import torch
import torch.nn as nn
import torch.nn.functional as F
import timm
from torchinfo import summary


class IPTEncoder(nn.Module):
    def __init__(self, latent_size=64, p=0.2, l2_normalize=True):
        super(IPTEncoder, self).__init__()

        self.inertial_encoder = nn.Sequential(  # input shape : (batch_size, 1, 603)
            nn.Flatten(),
            nn.Linear(201 * 3, 128),
            nn.Mish(),
            nn.Dropout(p),
            nn.Linear(128, latent_size // 2),
        )

        self.leg_encoder = nn.Sequential(  # input shape : (batch_size, 1, 900)
            nn.Flatten(),
            nn.Linear(25 * 36, 128),
            nn.Mish(),
            nn.Dropout(p),
            nn.Linear(128, latent_size // 2),
        )

        self.feet_encoder = nn.Sequential(  # input shape : (batch_size, 1, 500)
            nn.Flatten(),
            nn.Linear(25 * 20, 128),
            nn.Mish(),
            nn.Dropout(p),
            nn.Linear(128, latent_size // 2),
        )

        self.fc = nn.Sequential(
            nn.Linear(3 * latent_size // 2, latent_size), nn.Mish(), nn.Linear(latent_size, latent_size)
        )

        self.l2_normalize = l2_normalize

    def forward(self, inertial, leg, feet):
        inertial_features = self.inertial_encoder(inertial)
        leg_features = self.leg_encoder(leg)
        feet_features = self.feet_encoder(feet)

        combined_features = torch.cat([inertial_features, leg_features, feet_features], dim=1)
        nonvis_features = self.fc(combined_features)

        # Normalize
        if self.l2_normalize:
            nonvis_features = F.normalize(nonvis_features, dim=-1)

        return nonvis_features


class InertialEncoder(nn.Module):
    def __init__(self, latent_size=64, p=0.2, l2_normalize=True):
        super(InertialEncoder, self).__init__()

        self.inertial_encoder = nn.Sequential(  # input shape : (batch_size, 1, 1200)
            nn.Flatten(),
            nn.Linear(1200, 128),
            nn.Mish(),
            nn.Dropout(p),
            nn.Linear(128, latent_size),
        )

        self.l2_normalize = l2_normalize

    def forward(self, inertial):
        inertial_features = self.inertial_encoder(inertial)

        # Normalize
        if self.l2_normalize:
            inertial_features = F.normalize(inertial_features, dim=-1)

        return inertial_features


class VisualEncoder(nn.Module):
    def __init__(self, latent_size=64, replace_bn_w_gn=False, l2_normalize=True):
        super(VisualEncoder, self).__init__()
        self.encoder = timm.create_model("efficientnet_b0", pretrained=True)

        # Replace batchnorms with groupnorms if needed
        if replace_bn_w_gn:
            self.encoder = self.convert_bn_to_gn(self.encoder, features_per_group=16)

        # Remove the final classification layer
        self.encoder = nn.Sequential(*list(self.encoder.children())[:-1])

        # Fully connected layers
        self.fc = nn.Sequential(nn.Linear(1280, latent_size), nn.Mish(), nn.Linear(latent_size, latent_size))

        self.l2_normalize = l2_normalize

    def forward(self, x):
        vis_features = self.encoder(x)
        vis_features = self.fc(vis_features)
        if self.l2_normalize:
            vis_features = F.normalize(vis_features, dim=-1)
        return vis_features

    def convert_bn_to_gn(self, module, features_per_group=16):
        """Replace all BatchNorm layers with GroupNorm layers."""
        if isinstance(module, nn.BatchNorm2d):
            num_groups = max(1, module.num_features // features_per_group)
            return nn.GroupNorm(num_groups, module.num_features, eps=module.eps, affine=module.affine)

        for name, child_module in module.named_children():
            module.add_module(name, self.convert_bn_to_gn(child_module, features_per_group=features_per_group))

        return module


class VisualEncoderTiny(nn.Module):
    def __init__(self, latent_size=64, l2_normalize=True):
        super(VisualEncoderTiny, self).__init__()

        self.block1 = nn.Sequential(
            nn.Conv2d(3, 8, kernel_size=3, stride=1, padding=1, bias=False),
            nn.Mish(),
            nn.BatchNorm2d(8),  # output shape : (batch_size, 8, 64, 64),
            nn.MaxPool2d(kernel_size=2, stride=2),  # output shape : (batch_size, 8, 32, 32),
        )

        self.skipblock = nn.Sequential(
            nn.Conv2d(8, 8, kernel_size=3, stride=1, padding=1, bias=False),
            nn.Mish(),
            nn.BatchNorm2d(8),  # output shape : (batch_size, 8, 32, 32),
            nn.Conv2d(8, 8, kernel_size=3, stride=1, padding=1, bias=False),
            nn.Mish(),
            nn.BatchNorm2d(8),  # output shape : (batch_size, 8, 32, 32),
        )

        self.block2 = nn.Sequential(
            nn.Conv2d(8, 16, kernel_size=3, stride=1, padding=1, bias=False),
            nn.Mish(),
            nn.BatchNorm2d(16),  # output shape : (batch_size, 16, 32, 32),
            nn.MaxPool2d(kernel_size=2, stride=2),  # output shape : (batch_size, 16, 16, 16),
        )

        self.skipblock2 = nn.Sequential(
            nn.Conv2d(16, 16, kernel_size=3, stride=1, padding=1, bias=False),
            nn.Mish(),
            nn.BatchNorm2d(16),  # output shape : (batch_size, 16, 16, 16),
            nn.Conv2d(16, 16, kernel_size=3, stride=1, padding=1, bias=False),
            nn.Mish(),
            nn.BatchNorm2d(16),  # output shape : (batch_size, 16, 16, 16),
        )

        self.block3 = nn.Sequential(
            nn.Conv2d(16, 32, kernel_size=3, stride=1, padding=1, bias=False),
            nn.Mish(),
            nn.BatchNorm2d(32),  # output shape : (batch_size, 32, 16, 16),
            nn.AvgPool2d(kernel_size=2, stride=2),  # output shape : (batch_size, 32, 8, 8),
        )

        self.skipblock3 = nn.Sequential(
            nn.Conv2d(32, 32, kernel_size=3, stride=1, padding=1, bias=False),
            nn.Mish(),
            nn.BatchNorm2d(32),  # output shape : (batch_size, 32, 8, 8),
            nn.Conv2d(32, 32, kernel_size=3, stride=1, padding=1, bias=False),
            nn.Mish(),
            nn.BatchNorm2d(32),  # output shape : (batch_size, 32, 8, 8),
        )

        self.block4 = nn.Sequential(
            nn.Conv2d(32, 64, kernel_size=5, stride=3, padding=1, bias=False),
            nn.Mish(),
            nn.BatchNorm2d(64),  # output shape : (batch_size, 64, 2, 2),
        )

        self.skipblock4 = nn.Sequential(
            nn.Conv2d(64, 64, kernel_size=3, stride=1, padding=1, bias=False),
            nn.Mish(),
            nn.BatchNorm2d(64),  # output shape : (batch_size, 64, 2, 2),
            nn.Conv2d(64, 64, kernel_size=3, stride=1, padding=1, bias=False),
            nn.Mish(),
            nn.BatchNorm2d(64),  # output shape : (batch_size, 64, 2, 2),
        )

        self.fc = nn.Linear(256, latent_size)

        self.l2_normalize = l2_normalize

    def forward(self, x):
        x = self.block1(x)
        x = self.skipblock(x) + x
        x = self.block2(x)
        x = self.skipblock2(x) + x
        x = self.block3(x)
        x = self.skipblock3(x) + x
        x = self.block4(x)
        x = self.skipblock4(x) + x
        x = x.view(x.size(0), -1)  # Flatten to (batch_size, 256)

        x = self.fc(x)

        # Normalize
        if self.l2_normalize:
            x = F.normalize(x, dim=-1)

        return x


def visualize_models():
    # IPT Encoder
    ipt_encoder = IPTEncoder()
    inertial, leg, feet = torch.randn(1, 1, 603), torch.randn(1, 1, 900), torch.randn(1, 1, 500)
    out = ipt_encoder(inertial, leg, feet)
    print(out.shape)
    summary(ipt_encoder, [(1, 1, 603), (1, 1, 900), (1, 1, 500)])

    # Inertial Encoder
    inertial_encoder = InertialEncoder()
    inertial = torch.randn(1, 1, 603)
    out = inertial_encoder(inertial)
    print(out.shape)
    summary(inertial_encoder, (1, 1, 603))

    # Visual Encoder
    vision_encoder = VisualEncoder()
    x = torch.randn(1, 3, 64, 64)
    out = vision_encoder(x)
    print(out.shape)
    summary(vision_encoder, (1, 3, 64, 64))

    # Visual Encoder Tiny
    vision_encoder_tiny = VisualEncoderTiny()
    x = torch.randn(1, 3, 64, 64)
    out = vision_encoder_tiny(x)
    print(out.shape)
    summary(vision_encoder_tiny, (1, 3, 64, 64))
