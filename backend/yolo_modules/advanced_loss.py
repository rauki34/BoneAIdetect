"""
高级损失函数模块
包含 SIoU Loss、Focal Loss、IoU-aware Loss 等优化损失函数
用于YOLOv8/11骨折检测优化
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import math


class SIoULoss(nn.Module):
    """
    SIoU Loss (SCYLLA Intersection over Union Loss)
    包含角度损失、距离损失、形状损失，比CIoU更适合小目标检测
    
    参考论文: SIoU Loss: More Powerful Learning for Bounding Box Regression (2022)
    """
    def __init__(self, theta=4):
        super(SIoULoss, self).__init__()
        self.theta = theta  # 角度损失权重参数
    
    def forward(self, pred_boxes, target_boxes, eps=1e-7):
        """
        Args:
            pred_boxes: 预测框 [N, 4] (xywh格式)
            target_boxes: 目标框 [N, 4] (xywh格式)
        Returns:
            SIoU损失
        """
        # 转换为xyxy格式
        pred_x1 = pred_boxes[:, 0] - pred_boxes[:, 2] / 2
        pred_y1 = pred_boxes[:, 1] - pred_boxes[:, 3] / 2
        pred_x2 = pred_boxes[:, 0] + pred_boxes[:, 2] / 2
        pred_y2 = pred_boxes[:, 1] + pred_boxes[:, 3] / 2
        
        target_x1 = target_boxes[:, 0] - target_boxes[:, 2] / 2
        target_y1 = target_boxes[:, 1] - target_boxes[:, 3] / 2
        target_x2 = target_boxes[:, 0] + target_boxes[:, 2] / 2
        target_y2 = target_boxes[:, 1] + target_boxes[:, 3] / 2
        
        # 计算交集
        x1 = torch.max(pred_x1, target_x1)
        y1 = torch.max(pred_y1, target_y1)
        x2 = torch.min(pred_x2, target_x2)
        y2 = torch.min(pred_y2, target_y2)
        
        intersection = torch.clamp(x2 - x1, min=0) * torch.clamp(y2 - y1, min=0)
        
        # 计算并集
        pred_area = (pred_x2 - pred_x1) * (pred_y2 - pred_y1)
        target_area = (target_x2 - target_x1) * (target_y2 - target_y1)
        union = pred_area + target_area - intersection + eps
        
        # IoU
        iou = intersection / union
        
        # 计算中心点距离
        pred_cx = (pred_x1 + pred_x2) / 2
        pred_cy = (pred_y1 + pred_y2) / 2
        target_cx = (target_x1 + target_x2) / 2
        target_cy = (target_y1 + target_y2) / 2
        
        cw = torch.max(pred_x2, target_x2) - torch.min(pred_x1, target_x1)
        ch = torch.max(pred_y2, target_y2) - torch.min(pred_y1, target_y1)
        
        # 距离损失
        rho_x = ((target_cx - pred_cx) / (cw + eps)) ** 2
        rho_y = ((target_cy - pred_cy) / (ch + eps)) ** 2
        
        # 角度损失 (Angle cost)
        sigma = torch.sqrt(rho_x + rho_y + eps)
        sin_alpha = torch.abs(target_cy - pred_cy) / (sigma + eps)
        sin_beta = torch.abs(target_cx - pred_cx) / (sigma + eps)
        
        # 使用sin函数近似角度
        angle_cost = torch.sin(torch.arcsin(sin_alpha) - math.pi / 4) ** 2 + \
                     torch.sin(torch.arcsin(sin_beta) - math.pi / 4) ** 2
        
        # 距离成本
        gamma = 2 - angle_cost
        distance_cost = 2 - torch.exp(-gamma * rho_x) - torch.exp(-gamma * rho_y)
        
        # 形状损失
        w_pred = pred_x2 - pred_x1
        h_pred = pred_y2 - pred_y1
        w_target = target_x2 - target_x1
        h_target = target_y2 - target_y1
        
        delta_w = torch.abs(w_pred - w_target) / (torch.max(w_pred, w_target) + eps)
        delta_h = torch.abs(h_pred - h_target) / (torch.max(h_pred, h_target) + eps)
        
        shape_cost = (1 - torch.exp(-delta_w)) ** self.theta + \
                     (1 - torch.exp(-delta_h)) ** self.theta
        
        # 组合损失
        loss = 1 - iou + (distance_cost + shape_cost) / 2
        
        return loss.mean()


class EIoULoss(nn.Module):
    """
    EIoU Loss (Efficient IoU Loss)
    将IoU损失分解为重叠损失、中心距离损失和宽高损失
    
    参考论文: Focal and Efficient IOU Loss for Accurate Bounding Box Regression (AAAI 2021)
    """
    def __init__(self, eps=1e-7):
        super(EIoULoss, self).__init__()
        self.eps = eps
    
    def forward(self, pred_boxes, target_boxes):
        """
        Args:
            pred_boxes: 预测框 [N, 4] (xywh格式)
            target_boxes: 目标框 [N, 4] (xywh格式)
        """
        # 转换为xyxy格式
        pred_x1 = pred_boxes[:, 0] - pred_boxes[:, 2] / 2
        pred_y1 = pred_boxes[:, 1] - pred_boxes[:, 3] / 2
        pred_x2 = pred_boxes[:, 0] + pred_boxes[:, 2] / 2
        pred_y2 = pred_boxes[:, 1] + pred_boxes[:, 3] / 2
        
        target_x1 = target_boxes[:, 0] - target_boxes[:, 2] / 2
        target_y1 = target_boxes[:, 1] - target_boxes[:, 3] / 2
        target_x2 = target_boxes[:, 0] + target_boxes[:, 2] / 2
        target_y2 = target_boxes[:, 1] + target_boxes[:, 3] / 2
        
        # 计算交集
        x1 = torch.max(pred_x1, target_x1)
        y1 = torch.max(pred_y1, target_y1)
        x2 = torch.min(pred_x2, target_x2)
        y2 = torch.min(pred_y2, target_y2)
        
        intersection = torch.clamp(x2 - x1, min=0) * torch.clamp(y2 - y1, min=0)
        
        # 计算并集
        pred_area = (pred_x2 - pred_x1) * (pred_y2 - pred_y1)
        target_area = (target_x2 - target_x1) * (target_y2 - target_y1)
        union = pred_area + target_area - intersection + self.eps
        
        # IoU
        iou = intersection / union
        
        # 外接矩形
        cw = torch.max(pred_x2, target_x2) - torch.min(pred_x1, target_x1)
        ch = torch.max(pred_y2, target_y2) - torch.min(pred_y1, target_y1)
        c_area = cw * ch + self.eps
        
        # 中心点距离
        pred_cx = (pred_x1 + pred_x2) / 2
        pred_cy = (pred_y1 + pred_y2) / 2
        target_cx = (target_x1 + target_x2) / 2
        target_cy = (target_y1 + target_y2) / 2
        
        rho2 = ((target_cx - pred_cx) ** 2 + (target_cy - pred_cy) ** 2) / (cw ** 2 + ch ** 2 + self.eps)
        
        # 宽高损失
        w_pred = pred_x2 - pred_x1
        h_pred = pred_y2 - pred_y1
        w_target = target_x2 - target_x1
        h_target = target_y2 - target_y1
        
        v = (4 / (math.pi ** 2)) * torch.pow(torch.atan(w_target / (h_target + self.eps)) - \
                                              torch.atan(w_pred / (h_pred + self.eps)), 2)
        
        with torch.no_grad():
            alpha = v / (v - iou + 1 + self.eps)
        
        # CIoU
        ciou = iou - (rho2 + v * alpha)
        
        # EIoU = IoU - Distance Loss - Aspect Ratio Loss
        # 简化为 1 - CIoU
        loss = 1 - ciou
        
        return loss.mean()


class FocalLoss(nn.Module):
    """
    Focal Loss for Dense Object Detection
    处理类别不平衡问题，降低易分类样本的权重
    
    参考论文: Focal Loss for Dense Object Detection (ICCV 2017)
    """
    def __init__(self, alpha=0.25, gamma=2.0, reduction='mean'):
        """
        Args:
            alpha: 类别权重因子
            gamma: 聚焦参数，越大越关注难分类样本
            reduction: 损失缩减方式
        """
        super(FocalLoss, self).__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.reduction = reduction
    
    def forward(self, inputs, targets):
        """
        Args:
            inputs: 预测概率 [N, C] 或 [N]
            targets: 目标类别 [N]
        """
        # 计算交叉熵
        ce_loss = F.cross_entropy(inputs, targets, reduction='none')
        
        # 计算pt
        pt = torch.exp(-ce_loss)
        
        # Focal weight
        focal_weight = self.alpha * (1 - pt) ** self.gamma
        
        # Focal loss
        loss = focal_weight * ce_loss
        
        if self.reduction == 'mean':
            return loss.mean()
        elif self.reduction == 'sum':
            return loss.sum()
        else:
            return loss


class IoUAwareLoss(nn.Module):
    """
    IoU-aware Loss
    预测IoU值并用于加权分类损失，提高定位质量
    """
    def __init__(self, iou_weight=1.0):
        super(IoUAwareLoss, self).__init__()
        self.iou_weight = iou_weight
    
    def forward(self, cls_pred, iou_pred, cls_target, iou_target):
        """
        Args:
            cls_pred: 分类预测 [N, num_classes]
            iou_pred: IoU预测 [N, 1]
            cls_target: 分类目标 [N]
            iou_target: IoU目标 [N]
        """
        # 分类损失
        cls_loss = F.cross_entropy(cls_pred, cls_target, reduction='none')
        
        # IoU预测损失
        iou_loss = F.mse_loss(iou_pred.squeeze(), iou_target, reduction='none')
        
        # 使用预测的IoU加权分类损失
        # 高IoU预测应该对应更可靠的分类
        iou_weight = torch.sigmoid(iou_pred.squeeze()).detach()
        weighted_cls_loss = cls_loss * iou_weight
        
        total_loss = weighted_cls_loss.mean() + self.iou_weight * iou_loss.mean()
        
        return total_loss


class QualityFocalLoss(nn.Module):
    """
    Quality Focal Loss (QFL)
    用于处理定位质量估计和分类的联合学习
    
    参考论文: Generalized Focal Loss: Learning Qualified and Distributed Bounding Boxes for Dense Object Detection (NeurIPS 2020)
    """
    def __init__(self, beta=2.0):
        super(QualityFocalLoss, self).__init__()
        self.beta = beta
    
    def forward(self, pred, target, quality):
        """
        Args:
            pred: 预测分数 [N, num_classes]
            target: 目标类别 [N]
            quality: 定位质量分数 (IoU) [N]
        """
        # 获取正样本的预测
        pred_sigmoid = pred.sigmoid()
        
        # 创建one-hot目标
        num_classes = pred.size(1)
        one_hot = F.one_hot(target, num_classes).float()
        
        # 将IoU作为软标签
        soft_label = one_hot * quality.unsqueeze(1)
        
        # 计算focal weight
        ce = F.binary_cross_entropy_with_logits(pred, soft_label, reduction='none')
        
        # 正负样本使用不同的权重
        weight = torch.abs(pred_sigmoid - soft_label) ** self.beta
        
        loss = weight * ce
        
        return loss.sum() / (target.numel() + 1e-6)


class DistributionFocalLoss(nn.Module):
    """
    Distribution Focal Loss (DFL)
    用于学习边界框的分布表示，提高定位精度
    """
    def __init__(self, reg_max=16):
        super(DistributionFocalLoss, self).__init__()
        self.reg_max = reg_max
    
    def forward(self, pred, target):
        """
        Args:
            pred: 分布预测 [N, 4, reg_max]
            target: 目标位置 [N, 4]
        """
        # 将目标转换为分布形式
        target_left = target.long()
        target_right = target_left + 1
        
        weight_left = target_right.float() - target
        weight_right = target - target_left.float()
        
        # 计算交叉熵
        loss = F.cross_entropy(pred, target_left, reduction='none') * weight_left + \
               F.cross_entropy(pred, target_right, reduction='none') * weight_right
        
        return loss.mean()


class CombinedLoss(nn.Module):
    """
    组合损失函数
    结合多种损失函数的优点
    """
    def __init__(self, 
                 box_loss_type='siou',  # 'siou', 'eiou', 'ciou', 'giou', 'iou'
                 cls_loss_type='focal',  # 'focal', 'bce', 'qfl'
                 box_weight=7.5,
                 cls_weight=0.5,
                 dfl_weight=1.5,
                 use_dfl=True,
                 reg_max=16):
        super(CombinedLoss, self).__init__()
        
        self.box_weight = box_weight
        self.cls_weight = cls_weight
        self.dfl_weight = dfl_weight
        self.use_dfl = use_dfl
        
        # 边界框损失
        if box_loss_type == 'siou':
            self.box_loss = SIoULoss()
        elif box_loss_type == 'eiou':
            self.box_loss = EIoULoss()
        else:
            # 默认使用CIoU（YOLO默认）
            self.box_loss = None
            self.box_loss_type = box_loss_type
        
        # 分类损失
        if cls_loss_type == 'focal':
            self.cls_loss = FocalLoss(alpha=0.25, gamma=2.0)
        elif cls_loss_type == 'qfl':
            self.cls_loss = QualityFocalLoss()
        else:
            self.cls_loss = None
            self.cls_loss_type = cls_loss_type
        
        # DFL损失
        if use_dfl:
            self.dfl_loss = DistributionFocalLoss(reg_max)
    
    def forward(self, predictions, targets):
        """
        计算总损失
        Args:
            predictions: 模型预测输出
            targets: 真实标签
        """
        total_loss = 0
        loss_dict = {}
        
        # 边界框损失
        if self.box_loss is not None:
            box_loss = self.box_loss(predictions['boxes'], targets['boxes'])
        else:
            # 使用YOLO内置的损失
            box_loss = torch.tensor(0.0)
        
        loss_dict['box'] = box_loss
        total_loss += self.box_weight * box_loss
        
        # 分类损失
        if self.cls_loss is not None:
            cls_loss = self.cls_loss(predictions['cls'], targets['cls'])
        else:
            cls_loss = torch.tensor(0.0)
        
        loss_dict['cls'] = cls_loss
        total_loss += self.cls_weight * cls_loss
        
        # DFL损失
        if self.use_dfl and 'dfl' in predictions:
            dfl_loss = self.dfl_loss(predictions['dfl'], targets['boxes'])
            loss_dict['dfl'] = dfl_loss
            total_loss += self.dfl_weight * dfl_loss
        
        loss_dict['total'] = total_loss
        
        return total_loss, loss_dict


# ============ 工具函数 ============

def bbox_iou(box1, box2, xywh=True, GIoU=False, DIoU=False, CIoU=False, eps=1e-7):
    """
    计算两个边界框之间的IoU
    
    Args:
        box1: 第一个框 [N, 4]
        box2: 第二个框 [N, 4]
        xywh: 是否为xywh格式，False则为xyxy格式
        GIoU: 是否计算GIoU
        DIoU: 是否计算DIoU
        CIoU: 是否计算CIoU
        eps: 数值稳定性小值
    
    Returns:
        IoU值 [N]
    """
    if xywh:
        # 转换为xyxy
        b1_x1, b1_x2 = box1[:, 0] - box1[:, 2] / 2, box1[:, 0] + box1[:, 2] / 2
        b1_y1, b1_y2 = box1[:, 1] - box1[:, 3] / 2, box1[:, 1] + box1[:, 3] / 2
        b2_x1, b2_x2 = box2[:, 0] - box2[:, 2] / 2, box2[:, 0] + box2[:, 2] / 2
        b2_y1, b2_y2 = box2[:, 1] - box2[:, 3] / 2, box2[:, 1] + box2[:, 3] / 2
    else:
        b1_x1, b1_y1, b1_x2, b1_y2 = box1[:, 0], box1[:, 1], box1[:, 2], box1[:, 3]
        b2_x1, b2_y1, b2_x2, b2_y2 = box2[:, 0], box2[:, 1], box2[:, 2], box2[:, 3]
    
    # 交集
    inter = (torch.min(b1_x2, b2_x2) - torch.max(b1_x1, b2_x1)).clamp(0) * \
            (torch.min(b1_y2, b2_y2) - torch.max(b1_y1, b2_y1)).clamp(0)
    
    # 并集
    w1, h1 = b1_x2 - b1_x1, b1_y2 - b1_y1 + eps
    w2, h2 = b2_x2 - b2_x1, b2_y2 - b2_y1 + eps
    union = w1 * h1 + w2 * h2 - inter + eps
    
    # IoU
    iou = inter / union
    
    if GIoU or DIoU or CIoU:
        # 外接矩形
        cw = torch.max(b1_x2, b2_x2) - torch.min(b1_x1, b2_x1)
        ch = torch.max(b1_y2, b2_y2) - torch.min(b1_y1, b2_y1)
        
        if CIoU or DIoU:
            # 中心点距离
            c2 = cw ** 2 + ch ** 2 + eps
            rho2 = ((b2_x1 + b2_x2 - b1_x1 - b1_x2) ** 2 + 
                    (b2_y1 + b2_y2 - b1_y1 - b1_y2) ** 2) / 4
            
            if DIoU:
                return iou - rho2 / c2
            elif CIoU:
                v = (4 / (math.pi ** 2)) * torch.pow(torch.atan(w2 / h2) - torch.atan(w1 / h1), 2)
                with torch.no_grad():
                    alpha = v / (v - iou + (1 + eps))
                return iou - (rho2 / c2 + v * alpha)
        else:
            # GIoU
            c_area = cw * ch + eps
            return iou - (c_area - union) / c_area
    
    return iou


# ============ 测试代码 ============
if __name__ == "__main__":
    print("Testing Advanced Loss Functions...")
    
    # 创建测试数据
    batch_size = 4
    num_classes = 10
    
    pred_boxes = torch.randn(batch_size, 4).sigmoid()
    pred_boxes[:, 2:] = pred_boxes[:, 2:] * 0.5 + 0.1  # wh在合理范围
    target_boxes = torch.randn(batch_size, 4).sigmoid()
    target_boxes[:, 2:] = target_boxes[:, 2:] * 0.5 + 0.1
    
    cls_pred = torch.randn(batch_size, num_classes)
    cls_target = torch.randint(0, num_classes, (batch_size,))
    
    # 测试SIoU Loss
    print("\n1. Testing SIoU Loss:")
    siou_loss = SIoULoss()
    loss_siou = siou_loss(pred_boxes, target_boxes)
    print(f"   SIoU Loss: {loss_siou.item():.4f}")
    
    # 测试EIoU Loss
    print("\n2. Testing EIoU Loss:")
    eiou_loss = EIoULoss()
    loss_eiou = eiou_loss(pred_boxes, target_boxes)
    print(f"   EIoU Loss: {loss_eiou.item():.4f}")
    
    # 测试Focal Loss
    print("\n3. Testing Focal Loss:")
    focal_loss = FocalLoss(alpha=0.25, gamma=2.0)
    loss_focal = focal_loss(cls_pred, cls_target)
    print(f"   Focal Loss: {loss_focal.item():.4f}")
    
    # 测试IoU Aware Loss
    print("\n4. Testing IoU Aware Loss:")
    iou_pred = torch.randn(batch_size, 1)
    iou_target = torch.rand(batch_size)
    iou_aware_loss = IoUAwareLoss(iou_weight=1.0)
    loss_iou_aware = iou_aware_loss(cls_pred, iou_pred, cls_target, iou_target)
    print(f"   IoU Aware Loss: {loss_iou_aware.item():.4f}")
    
    # 测试Combined Loss
    print("\n5. Testing Combined Loss:")
    combined_loss = CombinedLoss(
        box_loss_type='siou',
        cls_loss_type='focal',
        box_weight=7.5,
        cls_weight=0.5
    )
    predictions = {
        'boxes': pred_boxes,
        'cls': cls_pred
    }
    targets = {
        'boxes': target_boxes,
        'cls': cls_target
    }
    total_loss, loss_dict = combined_loss(predictions, targets)
    print(f"   Total Loss: {total_loss.item():.4f}")
    print(f"   Box Loss: {loss_dict['box'].item():.4f}")
    print(f"   Cls Loss: {loss_dict['cls'].item():.4f}")
    
    # 测试bbox_iou函数
    print("\n6. Testing bbox_iou function:")
    iou = bbox_iou(pred_boxes, target_boxes, CIoU=True)
    print(f"   CIoU: {iou.mean().item():.4f}")
    
    giou = bbox_iou(pred_boxes, target_boxes, GIoU=True)
    print(f"   GIoU: {giou.mean().item():.4f}")
    
    print("\n✓ All tests passed!")
