"""
超参数优化模块
使用Optuna进行贝叶斯超参数优化
"""
import os
import sys
import time
from datetime import datetime
import optuna
from ultralytics import YOLO
import torch

from utils.logger import logger
# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class HyperparameterOptimizer:
    def __init__(self, data_yaml, base_model_path, output_dir, max_trials=20, n_epochs=50):
        """
        初始化超参数优化器
        
        Args:
            data_yaml: 数据集配置文件路径
            base_model_path: 基础模型路径
            output_dir: 输出目录
            max_trials: 最大尝试次数
            n_epochs: 每个尝试的训练轮数
        """
        self.data_yaml = data_yaml
        self.base_model_path = base_model_path
        self.output_dir = output_dir
        self.max_trials = max_trials
        self.n_epochs = n_epochs
        
    def objective(self, trial):
        """
        优化目标函数
        
        Args:
            trial: Optuna trial对象
        
        Returns:
            float: 验证mAP50值
        """
        # 超参数搜索空间
        params = {
            'optimizer': trial.suggest_categorical('optimizer', ['AdamW', 'SGD', 'RMSprop']),
            'lr0': trial.suggest_float('lr0', 1e-4, 1e-2, log=True),
            'lrf': trial.suggest_float('lrf', 1e-3, 1e-1, log=True),
            'momentum': trial.suggest_float('momentum', 0.8, 0.95),
            'weight_decay': trial.suggest_float('weight_decay', 1e-5, 1e-3, log=True),
            'warmup_epochs': trial.suggest_int('warmup_epochs', 1, 5),
            'batch': trial.suggest_categorical('batch', [8, 16, 24]),  # 适合6GB GPU的批次大小
            'patience': trial.suggest_int('patience', 20, 100),
            'mixup': trial.suggest_float('mixup', 0.0, 0.3),
            'degrees': trial.suggest_float('degrees', 0.0, 15.0),
            'scale': trial.suggest_float('scale', 0.3, 0.7),
            'cos_lr': trial.suggest_categorical('cos_lr', [True, False]),
        }
        
        # 生成唯一的trial名称
        trial_name = f"trial_{trial.number}_{int(time.time())}"
        project_dir = os.path.join(self.output_dir, 'hyperparameter_optimization')
        
        # 加载模型
        model = YOLO(self.base_model_path)
        
        # 训练参数
        train_args = {
            'data': self.data_yaml,
            'epochs': self.n_epochs,
            'batch': params['batch'],
            'imgsz': 640,
            'project': project_dir,
            'name': trial_name,
            'exist_ok': True,
            'verbose': False,
            'pretrained': True,
            'amp': True,
            'workers': 4,
            'cache': 'disk',
            'patience': params['patience'],
            'save': True,
            'save_period': -1,
            'device': 0 if torch.cuda.is_available() else 'cpu',
            'optimizer': params['optimizer'],
            'lr0': params['lr0'],
            'lrf': params['lrf'],
            'momentum': params['momentum'],
            'weight_decay': params['weight_decay'],
            'warmup_epochs': params['warmup_epochs'],
            'warmup_momentum': 0.8,
            'box': 7.5,
            'cls': 0.5,
            'dfl': 1.5,
            'hsv_h': 0.015,
            'hsv_s': 0.7,
            'hsv_v': 0.4,
            'degrees': params['degrees'],
            'translate': 0.1,
            'scale': params['scale'],
            'shear': 2.0,
            'perspective': 0.0,
            'flipud': 0.0,
            'fliplr': 0.5,
            'mosaic': 1.0,
            'mixup': params['mixup'],
            'copy_paste': 0.0,
            'auto_augment': 'randaugment',
            'erasing': 0.4,
            'crop_fraction': 1.0,
            'deterministic': False,
            'single_cls': False,
            'rect': False,
            'cos_lr': params['cos_lr'],
            'close_mosaic': 10,
            'resume': False,
            'fraction': 1.0,
            'profile': False,
            'freeze': None,
            'overlap_mask': True,
            'mask_ratio': 4,
            'dropout': 0.0,
            'val': True,
            'split': 'val',
        }
        
        logger.info(f"\n{'='*80}")
        logger.info(f"开始Trial {trial.number}")
        logger.info(f"参数: {params}")
        logger.info(f"{'='*80}")
        
        # 开始训练
        results = model.train(**train_args)
        
        # 获取验证结果
        if hasattr(results, 'metrics'):
            metrics = results.metrics
            map50 = metrics.get('metrics/mAP50(B)', 0.0)
            logger.info(f"Trial {trial.number} - mAP50: {map50:.4f}")
            return map50
        else:
            # 如果无法获取指标，返回0
            logger.info(f"Trial {trial.number} - 无法获取指标")
            return 0.0
    
    def optimize(self):
        """
        执行超参数优化
        
        Returns:
            dict: 最佳超参数
        """
        # 创建研究
        study = optuna.create_study(
            direction='maximize',
            sampler=optuna.samplers.TPESampler(),
            pruner=optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=10)
        )
        
        # 运行优化
        study.optimize(self.objective, n_trials=self.max_trials)
        
        # 打印结果
        logger.info(f"\n{'='*80}")
        logger.info("超参数优化完成")
        logger.info(f"最佳Trial: {study.best_trial.number}")
        logger.info(f"最佳mAP50: {study.best_value:.4f}")
        logger.info(f"最佳参数: {study.best_params}")
        logger.info(f"{'='*80}")
        
        return study.best_params

if __name__ == "__main__":
    # 示例用法
    import argparse
    
    parser = argparse.ArgumentParser(description='超参数优化')
    parser.add_argument('--data', type=str, required=True, help='数据集配置文件路径')
    parser.add_argument('--model', type=str, required=True, help='基础模型路径')
    parser.add_argument('--output', type=str, default='./runs', help='输出目录')
    parser.add_argument('--trials', type=int, default=20, help='最大尝试次数')
    parser.add_argument('--epochs', type=int, default=50, help='每个尝试的训练轮数')
    
    args = parser.parse_args()
    
    optimizer = HyperparameterOptimizer(
        data_yaml=args.data,
        base_model_path=args.model,
        output_dir=args.output,
        max_trials=args.trials,
        n_epochs=args.epochs
    )
    
    best_params = optimizer.optimize()
    
    # 保存最佳参数，文件名带日期时间戳
    import json
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'best_hyperparams_{timestamp}.json'
    with open(os.path.join(args.output, filename), 'w') as f:
        json.dump(best_params, f, indent=2)
    
    logger.info(f"最佳参数已保存到: {os.path.join(args.output, filename)}")
