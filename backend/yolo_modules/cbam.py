"""
CBAM (Convolutional Block Attention Module) 注意力机制模块
用于YOLOv8/11骨折检测优化

参考论文: CBAM: Convolutional Block Attention Module (ECCV 2018)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class ChannelAttention(nn.Module):
    """
    通道注意力模块
    通过学习通道间的关系，自动调整每个通道的权重
    """
    def __init__(self, channels, reduction_ratio=16):
        """
        Args:
            channels: 输入通道数
            reduction_ratio: 通道压缩比例，默认16
        """
        super(ChannelAttention, self).__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.max_pool = nn.AdaptiveMaxPool2d(1)
        
        # 共享MLP
        self.mlp = nn.Sequential(
            nn.Conv2d(channels, channels // reduction_ratio, 1, bias=False),
            nn.ReLU(inplace=True),
            nn.Conv2d(channels // reduction_ratio, channels, 1, bias=False)
        )
        
        self.sigmoid = nn.Sigmoid()
    
    def forward(self, x):
        """
        前向传播
        Args:
            x: 输入特征图 [B, C, H, W]
        Returns:
            加权后的特征图 [B, C, H, W]
        """
        # 平均池化分支
        avg_out = self.mlp(self.avg_pool(x))
        # 最大池化分支
        max_out = self.mlp(self.max_pool(x))
        # 融合并激活
        out = self.sigmoid(avg_out + max_out)
        return x * out


class SpatialAttention(nn.Module):
    """
    空间注意力模块
    通过学习空间位置的关系，自动调整每个空间位置的权重
    """
    def __init__(self, kernel_size=7):
        """
        Args:
            kernel_size: 卷积核大小，默认7
        """
        super(SpatialAttention, self).__init__()
        padding = kernel_size // 2
        self.conv = nn.Conv2d(2, 1, kernel_size, padding=padding, bias=False)
        self.sigmoid = nn.Sigmoid()
    
    def forward(self, x):
        """
        前向传播
        Args:
            x: 输入特征图 [B, C, H, W]
        Returns:
            加权后的特征图 [B, C, H, W]
        """
        # 计算通道维度的平均值和最大值
        avg_out = torch.mean(x, dim=1, keepdim=True)
        max_out, _ = torch.max(x, dim=1, keepdim=True)
        # 拼接
        x_cat = torch.cat([avg_out, max_out], dim=1)
        # 卷积和激活
        out = self.sigmoid(self.conv(x_cat))
        return x * out


class CBAM(nn.Module):
    """
    CBAM注意力模块
    结合通道注意力和空间注意力
    """
    def __init__(self, channels, reduction_ratio=16, spatial_kernel=7):
        """
        Args:
            channels: 输入通道数
            reduction_ratio: 通道压缩比例
            spatial_kernel: 空间注意力卷积核大小
        """
        super(CBAM, self).__init__()
        self.channel_attention = ChannelAttention(channels, reduction_ratio)
        self.spatial_attention = SpatialAttention(spatial_kernel)
    
    def forward(self, x):
        """
        前向传播
        Args:
            x: 输入特征图 [B, C, H, W]
        Returns:
            加权后的特征图 [B, C, H, W]
        """
        # 先应用通道注意力
        x = self.channel_attention(x)
        # 再应用空间注意力
        x = self.spatial_attention(x)
        return x


class Conv(nn.Module):
    """
    标准卷积层 (Conv + BN + SiLU)
  用于C2f_CBAM模块内部
    """
    default_act = nn.SiLU()
    
    def __init__(self, c1, c2, k=1, s=1, p=None, g=1, d=1, act=True):
        super().__init__()
        self.conv = nn.Conv2d(c1, c2, k, s, autopad(k, p, d), groups=g, dilation=d, bias=False)
        self.bn = nn.BatchNorm2d(c2)
        self.act = self.default_act if act is True else act if isinstance(act, nn.Module) else nn.Identity()
    
    def forward(self, x):
        return self.act(self.bn(self.conv(x)))


def autopad(k, p=None, d=1):
    """自动计算padding保持特征图尺寸"""
    if d > 1:
        k = d * (k - 1) + 1 if isinstance(k, int) else [d * (x - 1) + 1 for x in k]
    if p is None:
        p = k // 2 if isinstance(k, int) else [x // 2 for x in k]
    return p


class Bottleneck(nn.Module):
    """
    标准瓶颈结构
    """
    def __init__(self, c1, c2, shortcut=True, g=1, k=(3, 3), e=0.5):
        super().__init__()
        c_ = int(c2 * e)
        self.cv1 = Conv(c1, c_, k[0], 1)
        self.cv2 = Conv(c_, c2, k[1], 1, g=g)
        self.add = shortcut and c1 == c2
    
    def forward(self, x):
        return x + self.cv2(self.cv1(x)) if self.add else self.cv2(self.cv1(x))


class C2f_CBAM(nn.Module):
    """
    C2f模块 + CBAM注意力机制
    在YOLOv8的C2f模块基础上添加CBAM注意力
    
    适用于骨折检测场景:
    - 通道注意力帮助模型关注骨骼相关特征通道
    - 空间注意力帮助模型定位骨折区域
    """
    def __init__(self, c1, c2, n=1, shortcut=False, g=1, e=0.5):
        """
        Args:
            c1: 输入通道数
            c2: 输出通道数
            n: Bottleneck重复次数
            shortcut: 是否使用shortcut连接
            g: 分组卷积数
            e: 通道扩展比例
        """
        super().__init__()
        self.c = int(c2 * e)
        self.cv1 = Conv(c1, 2 * self.c, 1, 1)
        self.cv2 = Conv((2 + n) * self.c, c2, 1)
        self.m = nn.ModuleList(Bottleneck(self.c, self.c, shortcut, g, k=((3, 3), (3, 3)), e=1.0) for _ in range(n))
        # 添加CBAM注意力模块
        self.cbam = CBAM(c2, reduction_ratio=16)
    
    def forward(self, x):
        """
        前向传播
        """
        y = list(self.cv1(x).chunk(2, 1))
        y.extend(m(y[-1]) for m in self.m)
        out = self.cv2(torch.cat(y, 1))
        # 应用CBAM注意力
        out = self.cbam(out)
        return out
    
    def forward_split(self, x):
        """使用split代替chunk的前向传播"""
        y = self.cv1(x).split((self.c, self.c), 1)
        y = [y[0], y[1]]
        y.extend(m(y[-1]) for m in self.m)
        out = self.cv2(torch.cat(y, 1))
        out = self.cbam(out)
        return out


class C3_CBAM(nn.Module):
    """
    C3模块 + CBAM注意力机制
    适用于需要更强特征提取能力的场景
    """
    def __init__(self, c1, c2, n=1, shortcut=True, g=1, e=0.5):
        super().__init__()
        c_ = int(c2 * e)
        self.cv1 = Conv(c1, c_, 1, 1)
        self.cv2 = Conv(c1, c_, 1, 1)
        self.cv3 = Conv(2 * c_, c2, 1)
        self.m = nn.Sequential(*(Bottleneck(c_, c_, shortcut, g, k=((1, 1), (3, 3)), e=1.0) for _ in range(n)))
        self.cbam = CBAM(c2, reduction_ratio=16)
    
    def forward(self, x):
        out = self.cv3(torch.cat((self.m(self.cv1(x)), self.cv2(x)), 1))
        out = self.cbam(out)
        return out


# ============ 测试代码 ============
if __name__ == "__main__":
    # 测试CBAM模块
    print("Testing CBAM modules...")
    
    # 创建测试输入
    batch_size = 2
    channels = 64
    height, width = 32, 32
    x = torch.randn(batch_size, channels, height, width)
    
    # 测试ChannelAttention
    print("\n1. Testing ChannelAttention:")
    ca = ChannelAttention(channels, reduction_ratio=16)
    out_ca = ca(x)
    print(f"   Input shape: {x.shape}")
    print(f"   Output shape: {out_ca.shape}")
    assert out_ca.shape == x.shape, "ChannelAttention output shape mismatch"
    
    # 测试SpatialAttention
    print("\n2. Testing SpatialAttention:")
    sa = SpatialAttention(kernel_size=7)
    out_sa = sa(x)
    print(f"   Input shape: {x.shape}")
    print(f"   Output shape: {out_sa.shape}")
    assert out_sa.shape == x.shape, "SpatialAttention output shape mismatch"
    
    # 测试CBAM
    print("\n3. Testing CBAM:")
    cbam = CBAM(channels, reduction_ratio=16, spatial_kernel=7)
    out_cbam = cbam(x)
    print(f"   Input shape: {x.shape}")
    print(f"   Output shape: {out_cbam.shape}")
    assert out_cbam.shape == x.shape, "CBAM output shape mismatch"
    
    # 测试C2f_CBAM
    print("\n4. Testing C2f_CBAM:")
    c2f_cbam = C2f_CBAM(c1=64, c2=128, n=2, shortcut=True)
    out_c2f = c2f_cbam(x)
    print(f"   Input shape: {x.shape}")
    print(f"   Output shape: {out_c2f.shape}")
    
    # 测试C3_CBAM
    print("\n5. Testing C3_CBAM:")
    c3_cbam = C3_CBAM(c1=64, c2=128, n=2, shortcut=True)
    out_c3 = c3_cbam(x)
    print(f"   Input shape: {x.shape}")
    print(f"   Output shape: {out_c3.shape}")
    
    # 计算参数量
    def count_parameters(model):
        return sum(p.numel() for p in model.parameters() if p.requires_grad)
    
    print("\n6. Parameter counts:")
    print(f"   ChannelAttention: {count_parameters(ca):,}")
    print(f"   SpatialAttention: {count_parameters(sa):,}")
    print(f"   CBAM: {count_parameters(cbam):,}")
    print(f"   C2f_CBAM: {count_parameters(c2f_cbam):,}")
    print(f"   C3_CBAM: {count_parameters(c3_cbam):,}")
    
    print("\n✓ All tests passed!")
