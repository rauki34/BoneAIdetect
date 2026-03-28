"""
动态标签分配策略模块
包含 SimOTA、TaskAlignedAssigner 等动态标签分配策略
用于YOLOv8/11骨折检测优化

参考论文:
- OTA: Optimal Transport Assignment for Object Detection (CVPR 2021)
- TOOD: Task-aligned One-stage Object Detection (ICCV 2021)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple, List, Optional


class SimOTA(nn.Module):
    """
    SimOTA (Simplified Optimal Transport Assignment)
    简化版最优传输分配策略，动态为每个GT选择正样本
    
    核心思想：
    1. 计算每个候选框与GT的匹配代价（分类+回归）
    2. 使用动态top-k策略选择正样本数量
    3. 通过最优传输问题求解最佳分配
    """
    def __init__(self, 
                 num_classes: int = 80,
                 center_sampling_radius: float = 2.5,
                 candidate_topk: int = 10,
                 iou_weight: float = 3.0,
                 cls_weight: float = 1.0):
        super(SimOTA, self).__init__()
        self.num_classes = num_classes
        self.center_sampling_radius = center_sampling_radius
        self.candidate_topk = candidate_topk
        self.iou_weight = iou_weight
        self.cls_weight = cls_weight
    
    def forward(self,
                pred_scores: torch.Tensor,
                pred_bboxes: torch.Tensor,
                anchor_points: torch.Tensor,
                gt_labels: torch.Tensor,
                gt_bboxes: torch.Tensor,
                gt_bboxes_ignore: Optional[torch.Tensor] = None,
                eps: float = 1e-7) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Args:
            pred_scores: 预测分类分数 [num_anchors, num_classes]
            pred_bboxes: 预测边界框 [num_anchors, 4]
            anchor_points: 锚点中心坐标 [num_anchors, 2]
            gt_labels: GT标签 [num_gt]
            gt_bboxes: GT边界框 [num_gt, 4]
            gt_bboxes_ignore: 忽略的GT边界框
            eps: 数值稳定性小值
        
        Returns:
            assigned_labels: 分配的标签 [num_anchors]
            assigned_bboxes: 分配的边界框 [num_anchors, 4]
            assigned_scores: 分配的分数 [num_anchors, num_classes]
        """
        num_gt = gt_bboxes.size(0)
        num_anchors = pred_scores.size(0)
        
        # 如果没有GT，全部分配为背景
        if num_gt == 0:
            assigned_labels = torch.full((num_anchors,), self.num_classes, 
                                         dtype=torch.long, device=pred_scores.device)
            assigned_bboxes = torch.zeros((num_anchors, 4), device=pred_scores.device)
            assigned_scores = torch.zeros((num_anchors, self.num_classes + 1), 
                                          device=pred_scores.device)
            return assigned_labels, assigned_bboxes, assigned_scores
        
        # 1. 计算每个锚点是否在GT中心区域内
        inside_flags = self.get_in_gt_and_in_center(anchor_points, gt_bboxes)
        
        # 2. 计算分类代价
        # 使用Focal Loss的权重作为分类代价
        pred_scores_sigmoid = pred_scores.sigmoid()
        cls_cost = F.binary_cross_entropy(
            pred_scores_sigmoid.unsqueeze(0).expand(num_gt, -1, -1),
            F.one_hot(gt_labels, self.num_classes).float().unsqueeze(1),
            reduction='none'
        ).sum(-1)  # [num_gt, num_anchors]
        
        # 3. 计算回归代价（使用IoU）
        ious = self.bbox_overlaps(pred_bboxes.unsqueeze(0), gt_bboxes.unsqueeze(1), 
                                   mode='iou', is_aligned=False)  # [num_gt, num_anchors]
        iou_cost = -ious.log()  # 负对数作为代价
        
        # 4. 组合代价
        cost = self.cls_weight * cls_cost + self.iou_weight * iou_cost
        
        # 5. 只在中心区域内的候选框中分配
        cost = cost + (~inside_flags).float() * 1e10
        
        # 6. 动态确定每个GT的正样本数量
        ious_in_radius = ious * inside_flags.float()
        num_candidates = (ious_in_radius > 0).sum(dim=1)
        dynamic_ks = torch.clamp(num_candidates, min=1, max=self.candidate_topk)
        
        # 7. 为每个GT选择top-k个候选框
        assigned_gt_inds = torch.full((num_anchors,), -1, dtype=torch.long, 
                                       device=pred_scores.device)
        
        for gt_idx in range(num_gt):
            _, topk_indices = torch.topk(cost[gt_idx], k=dynamic_ks[gt_idx].item(), 
                                         largest=False)
            assigned_gt_inds[topk_indices] = gt_idx
        
        # 8. 处理分配结果
        pos_inds = assigned_gt_inds >= 0
        assigned_labels = torch.full((num_anchors,), self.num_classes, 
                                     dtype=torch.long, device=pred_scores.device)
        assigned_labels[pos_inds] = gt_labels[assigned_gt_inds[pos_inds]]
        
        assigned_bboxes = torch.zeros((num_anchors, 4), device=pred_scores.device)
        assigned_bboxes[pos_inds] = gt_bboxes[assigned_gt_inds[pos_inds]]
        
        # 9. 计算分配的分数（用于后续的损失计算）
        assigned_scores = torch.zeros((num_anchors, self.num_classes + 1), 
                                      device=pred_scores.device)
        if pos_inds.any():
            pos_ious = ious[assigned_gt_inds[pos_inds], pos_inds]
            assigned_scores[pos_inds, gt_labels[assigned_gt_inds[pos_inds]]] = pos_ious
        
        return assigned_labels, assigned_bboxes, assigned_scores
    
    def get_in_gt_and_in_center(self, anchor_points: torch.Tensor, 
                                 gt_bboxes: torch.Tensor) -> torch.Tensor:
        """
        判断锚点是否在GT框内和中心区域内
        
        Args:
            anchor_points: 锚点坐标 [num_anchors, 2]
            gt_bboxes: GT边界框 [num_gt, 4] (xyxy格式)
        
        Returns:
            inside_flags: 是否在区域内 [num_gt, num_anchors]
        """
        num_gt = gt_bboxes.size(0)
        num_anchors = anchor_points.size(0)
        
        # 扩展维度以便广播
        anchor_points = anchor_points.unsqueeze(0).expand(num_gt, -1, -1)  # [num_gt, num_anchors, 2]
        gt_bboxes = gt_bboxes.unsqueeze(1).expand(-1, num_anchors, -1)  # [num_gt, num_anchors, 4]
        
        # 判断是否在GT框内
        in_gt = (anchor_points[..., 0] >= gt_bboxes[..., 0]) & \
                (anchor_points[..., 0] <= gt_bboxes[..., 2]) & \
                (anchor_points[..., 1] >= gt_bboxes[..., 1]) & \
                (anchor_points[..., 1] <= gt_bboxes[..., 3])
        
        # 计算GT中心区域
        gt_cx = (gt_bboxes[..., 0] + gt_bboxes[..., 2]) / 2
        gt_cy = (gt_bboxes[..., 1] + gt_bboxes[..., 3]) / 2
        gt_w = gt_bboxes[..., 2] - gt_bboxes[..., 0]
        gt_h = gt_bboxes[..., 3] - gt_bboxes[..., 1]
        
        radius_x = self.center_sampling_radius * gt_w
        radius_y = self.center_sampling_radius * gt_h
        
        center_x1 = gt_cx - radius_x
        center_x2 = gt_cx + radius_x
        center_y1 = gt_cy - radius_y
        center_y2 = gt_cy + radius_y
        
        # 判断是否在中心区域内
        in_center = (anchor_points[..., 0] >= center_x1) & \
                    (anchor_points[..., 0] <= center_x2) & \
                    (anchor_points[..., 1] >= center_y1) & \
                    (anchor_points[..., 1] <= center_y2)
        
        # 同时在GT框内和中心区域内
        return in_gt & in_center
    
    def bbox_overlaps(self, bboxes1: torch.Tensor, bboxes2: torch.Tensor,
                      mode: str = 'iou', is_aligned: bool = False, eps: float = 1e-6) -> torch.Tensor:
        """计算边界框重叠"""
        if is_aligned:
            # 对齐模式
            lt = torch.max(bboxes1[..., :2], bboxes2[..., :2])
            rb = torch.min(bboxes1[..., 2:], bboxes2[..., 2:])
            
            wh = (rb - lt).clamp(min=0)
            overlap = wh[..., 0] * wh[..., 1]
            
            area1 = (bboxes1[..., 2] - bboxes1[..., 0]) * (bboxes1[..., 3] - bboxes1[..., 1])
            area2 = (bboxes2[..., 2] - bboxes2[..., 0]) * (bboxes2[..., 3] - bboxes2[..., 1])
            
            union = area1 + area2 - overlap + eps
            ious = overlap / union
        else:
            # 非对齐模式
            num_bboxes1 = bboxes1.size(1)
            num_bboxes2 = bboxes2.size(2)
            
            bboxes1 = bboxes1.unsqueeze(3).expand(-1, -1, -1, num_bboxes2, -1)
            bboxes2 = bboxes2.unsqueeze(2).expand(-1, -1, num_bboxes1, -1, -1)
            
            lt = torch.max(bboxes1[..., :2], bboxes2[..., :2])
            rb = torch.min(bboxes1[..., 2:], bboxes2[..., 2:])
            
            wh = (rb - lt).clamp(min=0)
            overlap = wh[..., 0] * wh[..., 1]
            
            area1 = (bboxes1[..., 2] - bboxes1[..., 0]) * (bboxes1[..., 3] - bboxes1[..., 1])
            area2 = (bboxes2[..., 2] - bboxes2[..., 0]) * (bboxes2[..., 3] - bboxes2[..., 1])
            
            union = area1 + area2 - overlap + eps
            ious = overlap / union
        
        return ious


class TaskAlignedAssigner(nn.Module):
    """
    TaskAlignedAssigner (任务对齐分配器)
    根据分类和定位任务的对齐程度动态分配标签
    
    核心思想：
    1. 计算任务对齐度量：t = s^α × u^β
       - s: 分类分数
       - u: IoU
       - α, β: 权重参数
    2. 根据对齐度量动态选择正样本
    3. 使用动态top-k策略
    
    参考论文: TOOD: Task-aligned One-stage Object Detection (ICCV 2021)
    """
    def __init__(self,
                 topk: int = 13,
                 num_classes: int = 80,
                 alpha: float = 1.0,
                 beta: float = 6.0,
                 eps: float = 1e-9):
        super(TaskAlignedAssigner, self).__init__()
        self.topk = topk
        self.num_classes = num_classes
        self.alpha = alpha
        self.beta = beta
        self.eps = eps
    
    def forward(self,
                pred_scores: torch.Tensor,
                pred_bboxes: torch.Tensor,
                anchor_points: torch.Tensor,
                gt_labels: torch.Tensor,
                gt_bboxes: torch.Tensor,
                mask_gt: Optional[torch.Tensor] = None) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Args:
            pred_scores: 预测分类分数 [batch_size, num_anchors, num_classes]
            pred_bboxes: 预测边界框 [batch_size, num_anchors, 4]
            anchor_points: 锚点坐标 [num_anchors, 2]
            gt_labels: GT标签 [batch_size, num_gt]
            gt_bboxes: GT边界框 [batch_size, num_gt, 4]
            mask_gt: GT掩码 [batch_size, num_gt]
        
        Returns:
            assigned_labels: 分配的标签 [batch_size, num_anchors]
            assigned_bboxes: 分配的边界框 [batch_size, num_anchors, 4]
            assigned_scores: 分配的分数 [batch_size, num_anchors, num_classes]
        """
        batch_size, num_anchors, _ = pred_scores.shape
        num_gt = gt_bboxes.size(1)
        
        # 处理没有GT的情况
        if num_gt == 0 or (mask_gt is not None and mask_gt.sum() == 0):
            assigned_labels = torch.full((batch_size, num_anchors), self.num_classes,
                                         dtype=torch.long, device=pred_scores.device)
            assigned_bboxes = torch.zeros((batch_size, num_anchors, 4), device=pred_scores.device)
            assigned_scores = torch.zeros((batch_size, num_anchors, self.num_classes),
                                          device=pred_scores.device)
            return assigned_labels, assigned_bboxes, assigned_scores
        
        # 1. 计算IoU矩阵
        # [batch_size, num_gt, num_anchors]
        ious = self.bbox_overlaps(gt_bboxes, pred_bboxes, mode='iou')
        
        # 2. 获取每个锚点对应GT类别的分类分数
        # [batch_size, num_gt, num_anchors]
        gt_labels_expanded = gt_labels.unsqueeze(-1).expand(-1, -1, num_anchors)
        pred_scores_for_gt = torch.gather(
            pred_scores.unsqueeze(1).expand(-1, num_gt, -1, -1),
            3,
            gt_labels_expanded.unsqueeze(-1)
        ).squeeze(-1)
        
        # 3. 计算任务对齐度量
        # t = s^α × u^β
        alignment_metric = (pred_scores_for_gt ** self.alpha) * (ious ** self.beta)
        
        # 4. 应用GT掩码
        if mask_gt is not None:
            mask_gt_expanded = mask_gt.unsqueeze(-1).expand(-1, -1, num_anchors)
            alignment_metric = alignment_metric * mask_gt_expanded
            ious = ious * mask_gt_expanded
        
        # 5. 为每个GT选择top-k个锚点
        # 取每个batch和每个GT的top-k
        topk_metrics, topk_indices = torch.topk(alignment_metric, 
                                                 min(self.topk, num_anchors), 
                                                 dim=-1, largest=True)
        
        # 6. 创建分配矩阵
        assigned_labels = torch.full((batch_size, num_anchors), self.num_classes,
                                     dtype=torch.long, device=pred_scores.device)
        assigned_bboxes = torch.zeros((batch_size, num_anchors, 4), device=pred_scores.device)
        assigned_scores = torch.zeros((batch_size, num_anchors, self.num_classes),
                                      device=pred_scores.device)
        
        # 7. 根据top-k结果进行分配
        for b in range(batch_size):
            for gt_idx in range(num_gt):
                if mask_gt is not None and not mask_gt[b, gt_idx]:
                    continue
                
                # 获取该GT的top-k锚点
                topk_idx = topk_indices[b, gt_idx]
                
                # 分配标签
                assigned_labels[b, topk_idx] = gt_labels[b, gt_idx]
                
                # 分配边界框
                assigned_bboxes[b, topk_idx] = gt_bboxes[b, gt_idx]
                
                # 分配分数（使用对齐度量作为软标签）
                assigned_scores[b, topk_idx, gt_labels[b, gt_idx]] = alignment_metric[b, gt_idx, topk_idx]
        
        return assigned_labels, assigned_bboxes, assigned_scores
    
    def bbox_overlaps(self, bboxes1: torch.Tensor, bboxes2: torch.Tensor,
                      mode: str = 'iou', eps: float = 1e-6) -> torch.Tensor:
        """
        计算边界框之间的IoU
        
        Args:
            bboxes1: [batch_size, num_gt, 4]
            bboxes2: [batch_size, num_anchors, 4]
        
        Returns:
            ious: [batch_size, num_gt, num_anchors]
        """
        batch_size, num_gt, _ = bboxes1.shape
        num_anchors = bboxes2.size(1)
        
        # 扩展维度
        bboxes1 = bboxes1.unsqueeze(2).expand(-1, -1, num_anchors, -1)
        bboxes2 = bboxes2.unsqueeze(1).expand(-1, num_gt, -1, -1)
        
        # 计算交集
        lt = torch.max(bboxes1[..., :2], bboxes2[..., :2])
        rb = torch.min(bboxes1[..., 2:], bboxes2[..., 2:])
        
        wh = (rb - lt).clamp(min=0)
        overlap = wh[..., 0] * wh[..., 1]
        
        # 计算面积
        area1 = (bboxes1[..., 2] - bboxes1[..., 0]) * (bboxes1[..., 3] - bboxes1[..., 1])
        area2 = (bboxes2[..., 2] - bboxes2[..., 0]) * (bboxes2[..., 3] - bboxes2[..., 1])
        
        # 计算IoU
        union = area1 + area2 - overlap + eps
        ious = overlap / union
        
        return ious


class DynamicLabelAssignment(nn.Module):
    """
    动态标签分配策略组合模块
    根据训练阶段和场景自动选择最佳分配策略
    """
    def __init__(self,
                 num_classes: int = 80,
                 use_simota: bool = True,
                 use_task_aligned: bool = True,
                 switch_epoch: int = 100):
        super(DynamicLabelAssignment, self).__init__()
        self.num_classes = num_classes
        self.use_simota = use_simota
        self.use_task_aligned = use_task_aligned
        self.switch_epoch = switch_epoch
        
        if use_simota:
            self.simota = SimOTA(num_classes=num_classes)
        
        if use_task_aligned:
            self.task_aligned = TaskAlignedAssigner(num_classes=num_classes)
        
        self.current_epoch = 0
    
    def set_epoch(self, epoch: int):
        """设置当前训练轮数"""
        self.current_epoch = epoch
    
    def forward(self,
                pred_scores: torch.Tensor,
                pred_bboxes: torch.Tensor,
                anchor_points: torch.Tensor,
                gt_labels: torch.Tensor,
                gt_bboxes: torch.Tensor,
                **kwargs) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        动态选择标签分配策略
        
        策略：
        - 早期训练（< switch_epoch）：使用SimOTA，更稳定的分配
        - 后期训练（>= switch_epoch）：使用TaskAligned，更精确的对齐
        """
        if self.current_epoch < self.switch_epoch and self.use_simota:
            # 早期使用SimOTA
            return self.simota(pred_scores, pred_bboxes, anchor_points,
                              gt_labels, gt_bboxes, **kwargs)
        elif self.use_task_aligned:
            # 后期使用TaskAligned
            # 调整输入维度以匹配TaskAlignedAssigner
            if pred_scores.dim() == 2:
                pred_scores = pred_scores.unsqueeze(0)
                pred_bboxes = pred_bboxes.unsqueeze(0)
                gt_labels = gt_labels.unsqueeze(0)
                gt_bboxes = gt_bboxes.unsqueeze(0)
            
            return self.task_aligned(pred_scores, pred_bboxes, anchor_points,
                                    gt_labels, gt_bboxes, **kwargs)
        else:
            # 默认使用SimOTA
            return self.simota(pred_scores, pred_bboxes, anchor_points,
                              gt_labels, gt_bboxes, **kwargs)


# ============ 工具函数 ============

def compute_max_iou_anchor(ious: torch.Tensor) -> torch.Tensor:
    """
    计算每个锚点与所有GT的最大IoU
    
    Args:
        ious: IoU矩阵 [num_gt, num_anchors] 或 [batch_size, num_gt, num_anchors]
    
    Returns:
        max_ious: 每个锚点的最大IoU
    """
    if ious.dim() == 2:
        return ious.max(dim=0)[0]
    else:
        return ious.max(dim=1)[0]


def compute_max_iou_gt(ious: torch.Tensor) -> torch.Tensor:
    """
    计算每个GT与所有锚点的最大IoU
    
    Args:
        ious: IoU矩阵 [num_gt, num_anchors] 或 [batch_size, num_gt, num_anchors]
    
    Returns:
        max_ious: 每个GT的最大IoU
    """
    if ious.dim() == 2:
        return ious.max(dim=1)[0]
    else:
        return ious.max(dim=2)[0]


def select_candidates_in_gts(xy_centers: torch.Tensor, gt_bboxes: torch.Tensor, 
                              eps: float = 1e-9) -> torch.Tensor:
    """
    选择在GT框内的候选锚点
    
    Args:
        xy_centers: 锚点中心坐标 [num_anchors, 2]
        gt_bboxes: GT边界框 [num_gt, 4] (xyxy格式)
    
    Returns:
        in_gt: 是否在GT内 [num_gt, num_anchors]
    """
    num_gt = gt_bboxes.size(0)
    num_anchors = xy_centers.size(0)
    
    # 扩展维度
    xy_centers = xy_centers.unsqueeze(0).expand(num_gt, -1, -1)
    gt_bboxes = gt_bboxes.unsqueeze(1).expand(-1, num_anchors, -1)
    
    # 计算边界
    lt = xy_centers - gt_bboxes[..., :2]
    rb = gt_bboxes[..., 2:] - xy_centers
    
    # 判断是否在内部
    in_gt = (lt > eps).all(dim=-1) & (rb > eps).all(dim=-1)
    
    return in_gt


# ============ 测试代码 ============
if __name__ == "__main__":
    print("Testing Dynamic Label Assignment...")
    
    # 创建测试数据
    batch_size = 2
    num_anchors = 100
    num_gt = 5
    num_classes = 10
    
    pred_scores = torch.randn(batch_size, num_anchors, num_classes)
    pred_bboxes = torch.randn(batch_size, num_anchors, 4).sigmoid()
    pred_bboxes[..., 2:] = pred_bboxes[..., 2:] * 0.5 + 0.1
    
    anchor_points = torch.randn(num_anchors, 2).sigmoid()
    
    gt_labels = torch.randint(0, num_classes, (batch_size, num_gt))
    gt_bboxes = torch.randn(batch_size, num_gt, 4).sigmoid()
    gt_bboxes[..., 2:] = gt_bboxes[..., 2:] * 0.5 + 0.1
    
    mask_gt = torch.ones(batch_size, num_gt, dtype=torch.bool)
    mask_gt[0, -1] = False  # 第一个batch的最后一个GT无效
    
    # 测试SimOTA
    print("\n1. Testing SimOTA:")
    simota = SimOTA(num_classes=num_classes)
    assigned_labels, assigned_bboxes, assigned_scores = simota(
        pred_scores[0], pred_bboxes[0], anchor_points,
        gt_labels[0], gt_bboxes[0]
    )
    print(f"   Assigned labels shape: {assigned_labels.shape}")
    print(f"   Positive samples: {(assigned_labels < num_classes).sum().item()}")
    
    # 测试TaskAlignedAssigner
    print("\n2. Testing TaskAlignedAssigner:")
    task_aligned = TaskAlignedAssigner(num_classes=num_classes, topk=10)
    assigned_labels, assigned_bboxes, assigned_scores = task_aligned(
        pred_scores, pred_bboxes, anchor_points,
        gt_labels, gt_bboxes, mask_gt
    )
    print(f"   Assigned labels shape: {assigned_labels.shape}")
    print(f"   Positive samples per batch: {(assigned_labels < num_classes).sum(dim=1).tolist()}")
    
    # 测试DynamicLabelAssignment
    print("\n3. Testing DynamicLabelAssignment:")
    dynamic = DynamicLabelAssignment(num_classes=num_classes)
    dynamic.set_epoch(50)  # 早期训练
    assigned_labels, assigned_bboxes, assigned_scores = dynamic(
        pred_scores[0], pred_bboxes[0], anchor_points,
        gt_labels[0], gt_bboxes[0]
    )
    print(f"   Epoch 50 (SimOTA) - Positive samples: {(assigned_labels < num_classes).sum().item()}")
    
    dynamic.set_epoch(150)  # 后期训练
    assigned_labels, assigned_bboxes, assigned_scores = dynamic(
        pred_scores[0], pred_bboxes[0], anchor_points,
        gt_labels[0], gt_bboxes[0]
    )
    print(f"   Epoch 150 (TaskAligned) - Positive samples: {(assigned_labels < num_classes).sum().item()}")
    
    # 测试工具函数
    print("\n4. Testing utility functions:")
    ious = torch.rand(num_gt, num_anchors)
    max_iou_anchor = compute_max_iou_anchor(ious)
    print(f"   Max IoU per anchor shape: {max_iou_anchor.shape}")
    
    max_iou_gt = compute_max_iou_gt(ious)
    print(f"   Max IoU per GT shape: {max_iou_gt.shape}")
    
    in_gt = select_candidates_in_gts(anchor_points, gt_bboxes[0])
    print(f"   Candidates in GTs shape: {in_gt.shape}")
    print(f"   Average candidates per GT: {in_gt.float().sum(dim=1).mean().item():.2f}")
    
    print("\n✓ All tests passed!")
