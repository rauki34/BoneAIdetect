"""
CBAM模型工具函数
提供创建带CBAM的YOLO模型的实用函数
"""

import torch.nn as nn
from ultralytics import YOLO
from ultralytics.nn.modules import C2f
from ultralytics.utils import LOGGER

# 导入CBAM模块
try:
    from .cbam import CBAM
except ImportError:
    from cbam import CBAM


class C2f_CBAM(C2f):
    """
    带CBAM的C2f模块
    继承自YOLO的C2f，在输出后添加CBAM注意力
    """
    def __init__(self, c1, c2, n=1, shortcut=False, g=1, e=0.5):
        super().__init__(c1, c2, n, shortcut, g, e)
        # 在C2f后添加CBAM
        self.cbam = CBAM(c2, reduction_ratio=16)

    def forward(self, x):
        """前向传播，添加CBAM"""
        x = super().forward(x)
        x = self.cbam(x)
        return x


def create_yolo_with_cbam(base_model='yolov8n.pt', nc=80, verbose=True, insert_strategy='deep_neck'):
    """
    创建带CBAM的YOLO模型

    方法：先加载标准YOLO模型，然后将C2f替换为C2f_CBAM

    插入策略：
    - 'all': 替换所有C2f模块（默认，计算量大）
    - 'deep_neck': 只在Backbone深层和Neck部分插入CBAM（推荐）
    - 'neck_only': 只在Neck部分插入CBAM
    - 'backbone_deep': 只在Backbone深层（后1/3）插入CBAM

    Args:
        base_model: 基础模型名称或路径
        nc: 类别数
        verbose: 是否打印详细信息
        insert_strategy: CBAM插入策略

    Returns:
        model: 带CBAM的YOLO模型
    """
    LOGGER.info(f"创建CBAM优化模型: {base_model}")
    LOGGER.info(f"插入策略: {insert_strategy}")

    # 加载基础模型
    model = YOLO(base_model)

    # 修改类别数（如果需要）
    if nc != model.model.nc:
        LOGGER.info(f"修改类别数: {model.model.nc} -> {nc}")
        model.model.nc = nc

    # 获取模型层数
    total_layers = len(list(model.model.model.named_children()))

    # 替换C2f为C2f_CBAM
    replaced_count = 0
    for i, (name, module) in enumerate(model.model.model.named_children()):
        # 只替换C2f，不替换C2f_CBAM（避免重复替换）
        if type(module).__name__ == 'C2f':
            should_replace = False
            layer_position = ""

            if insert_strategy == 'all':
                # 替换所有C2f
                should_replace = True
                layer_position = "all"
            elif insert_strategy == 'deep_neck':
                # Backbone深层（后1/3）和Neck部分
                # 通常YOLOv8/11结构：Backbone(0-9层) + Neck(10-21层) + Head(22+层)
                if i >= total_layers * 0.6:  # 后40%的层（深层Backbone + Neck）
                    should_replace = True
                    layer_position = "deep/neck"
            elif insert_strategy == 'neck_only':
                # 只在Neck部分（通常Backbone之后）
                if i >= total_layers * 0.7:  # 后30%的层（主要是Neck）
                    should_replace = True
                    layer_position = "neck"
            elif insert_strategy == 'backbone_deep':
                # 只在Backbone深层（中间到后1/3）
                if total_layers * 0.4 <= i < total_layers * 0.7:
                    should_replace = True
                    layer_position = "backbone_deep"

            if should_replace:
                # 获取C2f的参数
                c1 = module.cv1.conv.in_channels
                c2 = module.cv2.conv.out_channels
                n = len(module.m)
                shortcut = module.m[0].add if len(module.m) > 0 else False

                # 创建带CBAM的C2f
                c2f_cbam = C2f_CBAM(c1, c2, n, shortcut, g=1, e=0.5)

                # 复制权重
                c2f_cbam.cv1 = module.cv1
                c2f_cbam.cv2 = module.cv2
                c2f_cbam.m = module.m

                # 替换模块
                model.model.model[int(name)] = c2f_cbam

                replaced_count += 1
                if verbose:
                    LOGGER.info(f"  ✓ 层 {i} ({layer_position}): C2f -> C2f_CBAM ({c2}ch)")

    LOGGER.info(f"✓ 共替换 {replaced_count}/{total_layers} 个C2f模块为C2f_CBAM")

    # 打印模型信息
    total_params = sum(p.numel() for p in model.model.parameters())
    cbam_params = sum(p.numel() for name, module in model.model.named_modules()
                      if 'CBAM' in type(module).__name__ for p in module.parameters())
    LOGGER.info(f"✓ 模型总参数量: {total_params:,}")
    LOGGER.info(f"✓ CBAM参数量: {cbam_params:,} ({cbam_params/total_params*100:.2f}%)")

    return model


# 测试
if __name__ == "__main__":
    print("测试CBAM YOLO模型创建...")

    try:
        # 创建模型
        model = create_yolo_with_cbam('yolov8n.pt', nc=80, verbose=True)
        print("\n✓ CBAM模型创建成功!")

        # 统计CBAM模块数量
        cbam_count = 0
        for name, module in model.model.named_modules():
            if 'CBAM' in type(module).__name__:
                cbam_count += 1

        print(f"✓ 模型中包含 {cbam_count} 个CBAM相关模块")

        # 测试前向传播
        import torch
        x = torch.randn(1, 3, 640, 640)
        with torch.no_grad():
            output = model.model(x)
        print(f"✓ 前向传播成功")
        print(f"  输出形状: {[o.shape for o in output]}")

    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()
