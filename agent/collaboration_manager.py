"""
Agent协作管理器

功能：
- Agent间通信与协调
- 任务编排与分配
- 数据共享与同步
- 决策融合
- 错误处理与恢复
- 性能监控

架构：
- 协作总线（Collaboration Bus）
- 任务队列（Task Queue）
- 数据共享层（Data Sharing Layer）
- 决策融合器（Decision Fusion）
- 监控系统（Monitoring System）
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import queue
import uuid

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskPriority(Enum):
    """任务优先级"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

class AgentType(Enum):
    """Agent类型"""
    CLIMATE = "climate"
    CROP = "crop"
    GROWTH = "growth"
    ECO = "eco"
    MARKET = "market"
    FINANCE = "finance"
    RISK = "risk"
    PEST = "pest"
    NUTRITION = "nutrition"
    SEASON = "season"
    SOIL = "soil"

@dataclass
class Task:
    """任务数据类"""
    id: str
    name: str
    description: str
    agent_type: AgentType
    priority: TaskPriority
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    data: Dict[str, Any] = None
    result: Dict[str, Any] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    dependencies: List[str] = None
    timeout: int = 300  # 默认5分钟超时
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.data is None:
            self.data = {}

@dataclass
class AgentMessage:
    """Agent消息数据类"""
    id: str
    from_agent: str
    to_agent: str
    message_type: str
    content: Dict[str, Any]
    timestamp: datetime
    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "id": self.id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "message_type": self.message_type,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "reply_to": self.reply_to
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'AgentMessage':
        """从字典创建消息"""
        return cls(
            id=data["id"],
            from_agent=data["from_agent"],
            to_agent=data["to_agent"],
            message_type=data["message_type"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            correlation_id=data.get("correlation_id"),
            reply_to=data.get("reply_to")
        )

class CollaborationBus:
    """协作总线"""
    
    def __init__(self):
        self.message_queue = queue.Queue()
        self.message_handlers = {}
        self.subscribers = {}
        self.running = False
        self.thread = None
        
    def start(self):
        """启动协作总线"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._process_messages)
            self.thread.daemon = True
            self.thread.start()
            logger.info("Collaboration bus started")
    
    def stop(self):
        """停止协作总线"""
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join()
            logger.info("Collaboration bus stopped")
    
    def register_handler(self, message_type: str, handler: Callable):
        """注册消息处理器"""
        self.message_handlers[message_type] = handler
        logger.info(f"Registered handler for message type: {message_type}")
    
    def subscribe(self, agent_id: str, message_types: List[str]):
        """订阅消息"""
        if agent_id not in self.subscribers:
            self.subscribers[agent_id] = []
        
        for msg_type in message_types:
            if msg_type not in self.subscribers[agent_id]:
                self.subscribers[agent_id].append(msg_type)
        
        logger.info(f"Agent {agent_id} subscribed to messages: {message_types}")
    
    def publish(self, message: AgentMessage):
        """发布消息"""
        self.message_queue.put(message)
        logger.info(f"Published message {message.id} from {message.from_agent} to {message.to_agent}")
    
    def send_direct(self, to_agent: str, message_type: str, content: Dict[str, Any],
                   correlation_id: Optional[str] = None):
        """发送直接消息"""
        message = AgentMessage(
            id=str(uuid.uuid4()),
            from_agent="system",
            to_agent=to_agent,
            message_type=message_type,
            content=content,
            timestamp=datetime.now(),
            correlation_id=correlation_id
        )
        self.publish(message)
    
    def _process_messages(self):
        """处理消息"""
        while self.running:
            try:
                message = self.message_queue.get(timeout=1)
                
                # 处理消息
                if message.message_type in self.message_handlers:
                    handler = self.message_handlers[message.message_type]
                    try:
                        handler(message)
                    except Exception as e:
                        logger.error(f"Error handling message {message.id}: {e}")
                else:
                    # 转发给订阅者
                    self._route_message(message)
                
                self.message_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing messages: {e}")
    
    def _route_message(self, message: AgentMessage):
        """路由消息到订阅者"""
        for agent_id, subscribed_types in self.subscribers.items():
            if message.message_type in subscribed_types:
                # 创建副本转发给订阅者
                forwarded_message = AgentMessage(
                    id=str(uuid.uuid4()),
                    from_agent=message.from_agent,
                    to_agent=agent_id,
                    message_type=message.message_type,
                    content=message.content,
                    timestamp=datetime.now(),
                    correlation_id=message.correlation_id,
                    reply_to=message.id
                )
                self.publish(forwarded_message)

class TaskQueue:
    """任务队列"""
    
    def __init__(self):
        self.tasks = {}
        self.pending_queue = queue.PriorityQueue()
        self.running_tasks = {}
        self.completed_tasks = []
        self.lock = threading.Lock()
        self.task_callbacks = {}
        
    def add_task(self, task: Task):
        """添加任务"""
        with self.lock:
            self.tasks[task.id] = task
            # 使用优先级排序
            priority_value = -task.priority.value  # 负数用于降序排列
            self.pending_queue.put((priority_value, task.id))
            
            logger.info(f"Added task {task.id}: {task.name}")
    
    def get_next_task(self) -> Optional[Task]:
        """获取下一个任务"""
        with self.lock:
            try:
                while not self.pending_queue.empty():
                    priority, task_id = self.pending_queue.get_nowait()
                    task = self.tasks.get(task_id)
                    
                    if task and task.status == TaskStatus.PENDING:
                        # 检查依赖
                        if self._check_dependencies(task):
                            task.status = TaskStatus.RUNNING
                            task.started_at = datetime.now()
                            self.running_tasks[task_id] = task
                            return task
                        else:
                            # 依赖未满足，重新加入队列
                            self.pending_queue.put((priority, task_id))
                
                return None
                
            except queue.Empty:
                return None
    
    def complete_task(self, task_id: str, result: Dict[str, Any] = None, error: str = None):
        """完成任务"""
        with self.lock:
            task = self.tasks.get(task_id)
            if task:
                task.status = TaskStatus.COMPLETED if error is None else TaskStatus.FAILED
                task.completed_at = datetime.now()
                task.result = result
                task.error = error
                
                # 从运行中移除
                self.running_tasks.pop(task_id, None)
                
                # 添加到已完成列表
                if task.status == TaskStatus.COMPLETED:
                    self.completed_tasks.append(task)
                
                # 调用回调函数
                if task_id in self.task_callbacks:
                    callback = self.task_callbacks[task_id]
                    try:
                        callback(task)
                    except Exception as e:
                        logger.error(f"Error executing task callback for {task_id}: {e}")
                
                logger.info(f"Task {task_id} completed with status: {task.status}")
    
    def retry_task(self, task_id: str):
        """重试任务"""
        with self.lock:
            task = self.tasks.get(task_id)
            if task and task.status == TaskStatus.FAILED:
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    task.status = TaskStatus.PENDING
                    task.started_at = None
                    task.completed_at = None
                    task.error = None
                    
                    # 重新加入队列
                    priority_value = -task.priority.value
                    self.pending_queue.put((priority_value, task_id))
                    
                    logger.info(f"Retrying task {task_id} (attempt {task.retry_count})")
                else:
                    logger.error(f"Task {task_id} exceeded max retries")
    
    def _check_dependencies(self, task: Task) -> bool:
        """检查任务依赖"""
        if not task.dependencies:
            return True
        
        for dep_id in task.dependencies:
            dep_task = self.tasks.get(dep_id)
            if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                return False
        
        return True
    
    def register_callback(self, task_id: str, callback: Callable):
        """注册任务完成回调"""
        self.task_callbacks[task_id] = callback
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态"""
        task = self.tasks.get(task_id)
        return task.status if task else None
    
    def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务结果"""
        task = self.tasks.get(task_id)
        return task.result if task and task.status == TaskStatus.COMPLETED else None

class DataSharingLayer:
    """数据共享层"""
    
    def __init__(self):
        self.shared_data = {}
        self.data_locks = {}
        self.subscribers = {}
        self.cache_dir = os.path.join(os.path.dirname(__file__), "..", "data", "shared_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        
    def store_data(self, key: str, data: Any, agent_id: str = None):
        """存储共享数据"""
        with self._get_lock(key):
            self.shared_data[key] = {
                "data": data,
                "agent_id": agent_id,
                "timestamp": datetime.now(),
                "version": self._get_version(key) + 1
            }
            
            # 通知订阅者
            self._notify_subscribers(key, "data_updated", data)
            
            # 持久化到缓存
            self._cache_data(key, data)
            
            logger.info(f"Data stored at key: {key}")
    
    def get_data(self, key: str, agent_id: str = None) -> Any:
        """获取共享数据"""
        with self._get_lock(key):
            if key in self.shared_data:
                data_info = self.shared_data[key]
                return data_info["data"]
            else:
                # 尝试从缓存加载
                cached_data = self._load_cached_data(key)
                if cached_data:
                    self.shared_data[key] = {
                        "data": cached_data,
                        "agent_id": "system",
                        "timestamp": datetime.now(),
                        "version": 1
                    }
                    return cached_data
        
        return None
    
    def subscribe_to_data(self, key: str, agent_id: str, callback: Callable):
        """订阅数据变化"""
        if key not in self.subscribers:
            self.subscribers[key] = []
        
        self.subscribers[key].append({
            "agent_id": agent_id,
            "callback": callback
        })
        
        logger.info(f"Agent {agent_id} subscribed to data key: {key}")
    
    def _get_lock(self, key: str):
        """获取数据锁"""
        if key not in self.data_locks:
            self.data_locks[key] = threading.Lock()
        return self.data_locks[key]
    
    def _get_version(self, key: str) -> int:
        """获取数据版本"""
        if key in self.shared_data:
            return self.shared_data[key]["version"]
        return 0
    
    def _notify_subscribers(self, key: str, event_type: str, data: Any):
        """通知订阅者"""
        if key in self.subscribers:
            for subscriber in self.subscribers[key]:
                try:
                    subscriber["callback"](event_type, data, key)
                except Exception as e:
                    logger.error(f"Error notifying subscriber {subscriber['agent_id']}: {e}")
    
    def _cache_data(self, key: str, data: Any):
        """缓存数据"""
        cache_file = os.path.join(self.cache_dir, f"{key}.json")
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "data": data,
                    "timestamp": datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to cache data for key {key}: {e}")
    
    def _load_cached_data(self, key: str) -> Any:
        """加载缓存数据"""
        cache_file = os.path.join(self.cache_dir, f"{key}.json")
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)
                return cached["data"]
        except Exception as e:
            logger.error(f"Failed to load cached data for key {key}: {e}")
            return None

class DecisionFusion:
    """决策融合器"""
    
    def __init__(self):
        self.decision_history = []
        self.fusion_strategies = {
            "majority_vote": self._majority_vote_fusion,
            "weighted_average": self._weighted_average_fusion,
            "confidence_based": self._confidence_based_fusion,
            "rule_based": self._rule_based_fusion
        }
    
    def fuse_decisions(self, decisions: List[Dict], strategy: str = "confidence_based") -> Dict:
        """融合多个决策"""
        
        if strategy not in self.fusion_strategies:
            raise ValueError(f"Unknown fusion strategy: {strategy}")
        
        fusion_func = self.fusion_strategies[strategy]
        result = fusion_func(decisions)
        
        # 记录融合历史
        fusion_record = {
            "timestamp": datetime.now().isoformat(),
            "strategy": strategy,
            "input_decisions": decisions,
            "fused_decision": result,
            "confidence": self._calculate_fusion_confidence(decisions)
        }
        self.decision_history.append(fusion_record)
        
        logger.info(f"Decisions fused using strategy: {strategy}")
        return result
    
    def _majority_vote_fusion(self, decisions: List[Dict]) -> Dict:
        """多数投票融合"""
        
        # 简化的多数投票逻辑
        vote_counts = {}
        for decision in decisions:
            choice = decision.get("choice", "unknown")
            vote_counts[choice] = vote_counts.get(choice, 0) + 1
        
        # 获得最多票数的选项
        majority_choice = max(vote_counts, key=vote_counts.get)
        
        return {
            "choice": majority_choice,
            "confidence": vote_counts[majority_choice] / len(decisions),
            "method": "majority_vote"
        }
    
    def _weighted_average_fusion(self, decisions: List[Dict]) -> Dict:
        """加权平均融合"""
        
        total_weight = 0
        weighted_sum = 0
        
        for decision in decisions:
            weight = decision.get("weight", 1.0)
            score = decision.get("score", 0.5)
            weighted_sum += score * weight
            total_weight += weight
        
        average_score = weighted_sum / total_weight if total_weight > 0 else 0.5
        
        return {
            "score": average_score,
            "confidence": min(total_weight / len(decisions), 1.0),
            "method": "weighted_average"
        }
    
    def _confidence_based_fusion(self, decisions: List[Dict]) -> Dict:
        """基于置信度的融合"""
        
        # 按置信度排序
        sorted_decisions = sorted(decisions, key=lambda x: x.get("confidence", 0), reverse=True)
        
        # 取最高置信度的决策
        best_decision = sorted_decisions[0]
        
        # 计算融合置信度
        avg_confidence = sum(d.get("confidence", 0) for d in decisions) / len(decisions)
        
        return {
            **best_decision,
            "confidence": avg_confidence,
            "method": "confidence_based"
        }
    
    def _rule_based_fusion(self, decisions: List[Dict]) -> Dict:
        """基于规则的融合"""
        
        # 简化的规则融合逻辑
        if len(decisions) == 1:
            return decisions[0]
        
        # 检查是否有冲突
        choices = [d.get("choice", "unknown") for d in decisions]
        if len(set(choices)) == 1:
            # 一致决策
            return decisions[0]
        else:
            # 冲突决策，使用最高置信度
            best_decision = max(decisions, key=lambda x: x.get("confidence", 0))
            return {
                **best_decision,
                "conflict": True,
                "method": "rule_based"
            }
    
    def _calculate_fusion_confidence(self, decisions: List[Dict]) -> float:
        """计算融合置信度"""
        
        if not decisions:
            return 0.0
        
        # 基于决策一致性和置信度计算
        confidence_scores = [d.get("confidence", 0) for d in decisions]
        avg_confidence = sum(confidence_scores) / len(confidence_scores)
        
        # 检查决策一致性
        choices = [d.get("choice", "unknown") for d in decisions]
        consistency = 1.0 if len(set(choices)) == 1 else 0.5
        
        return avg_confidence * consistency

class MonitoringSystem:
    """监控系统"""
    
    def __init__(self):
        self.metrics = {}
        self.alerts = []
        self.performance_data = {}
        self.health_status = {}
        
    def record_metric(self, name: str, value: float, tags: Dict[str, str] = None):
        """记录性能指标"""
        
        if name not in self.metrics:
            self.metrics[name] = []
        
        metric_entry = {
            "timestamp": datetime.now().isoformat(),
            "value": value,
            "tags": tags or {}
        }
        
        self.metrics[name].append(metric_entry)
        
        # 检查阈值
        self._check_metric_threshold(name, value, tags)
        
        logger.debug(f"Recorded metric {name}: {value}")
    
    def _check_metric_threshold(self, name: str, value: float, tags: Dict[str, str]):
        """检查指标阈值"""
        
        thresholds = {
            "task_completion_time": {"warning": 300, "critical": 600},
            "error_rate": {"warning": 0.1, "critical": 0.2},
            "memory_usage": {"warning": 0.8, "critical": 0.9},
            "cpu_usage": {"warning": 0.8, "critical": 0.9}
        }
        
        if name in thresholds:
            threshold = thresholds[name]
            
            if value > threshold["critical"]:
                self._create_alert(name, "critical", value, tags)
            elif value > threshold["warning"]:
                self._create_alert(name, "warning", value, tags)
    
    def _create_alert(self, metric_name: str, severity: str, value: float, tags: Dict[str, str]):
        """创建警报"""
        
        alert = {
            "id": str(uuid.uuid4()),
            "metric_name": metric_name,
            "severity": severity,
            "value": value,
            "tags": tags,
            "timestamp": datetime.now().isoformat(),
            "message": f"{metric_name} is {severity}: {value}"
        }
        
        self.alerts.append(alert)
        logger.warning(f"Alert created: {alert['message']}")
    
    def get_metrics(self, name: str = None, time_range: int = 3600) -> Dict:
        """获取指标数据"""
        
        if name:
            if name in self.metrics:
                # 过滤时间范围内的数据
                cutoff_time = datetime.now() - timedelta(seconds=time_range)
                recent_data = [
                    entry for entry in self.metrics[name]
                    if datetime.fromisoformat(entry["timestamp"]) > cutoff_time
                ]
                return {name: recent_data}
            else:
                return {}
        else:
            # 返回所有指标
            result = {}
            for metric_name, data in self.metrics.items():
                cutoff_time = datetime.now() - timedelta(seconds=time_range)
                recent_data = [
                    entry for entry in data
                    if datetime.fromisoformat(entry["timestamp"]) > cutoff_time
                ]
                if recent_data:
                    result[metric_name] = recent_data
            return result
    
    def get_alerts(self, severity: str = None, limit: int = 100) -> List[Dict]:
        """获取警报"""
        
        if severity:
            alerts = [alert for alert in self.alerts if alert["severity"] == severity]
        else:
            alerts = self.alerts
        
        return alerts[-limit:]  # 返回最新的limit个警报
    
    def update_health_status(self, agent_id: str, status: str, details: Dict = None):
        """更新健康状态"""
        
        self.health_status[agent_id] = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }
        
        logger.info(f"Health status updated for {agent_id}: {status}")
    
    def get_health_status(self, agent_id: str = None) -> Dict:
        """获取健康状态"""
        
        if agent_id:
            return self.health_status.get(agent_id, {})
        else:
            return self.health_status

class CollaborationManager:
    """协作管理器"""
    
    def __init__(self):
        self.collaboration_bus = CollaborationBus()
        self.task_queue = TaskQueue()
        self.data_sharing = DataSharingLayer()
        self.decision_fusion = DecisionFusion()
        self.monitoring = MonitoringSystem()
        
        self.agents = {}
        self.running = False
        
        # 注册协作总线处理器
        self.collaboration_bus.register_handler("task_result", self._handle_task_result)
        self.collaboration_bus.register_handler("data_request", self._handle_data_request)
        self.collaboration_bus.register_handler("decision_request", self._handle_decision_request)
        
    def start(self):
        """启动协作管理器"""
        if not self.running:
            self.running = True
            self.collaboration_bus.start()
            
            # 启动任务处理线程
            self._start_task_processor()
            
            logger.info("Collaboration manager started")
    
    def stop(self):
        """停止协作管理器"""
        if self.running:
            self.running = False
            self.collaboration_bus.stop()
            logger.info("Collaboration manager stopped")
    
    def register_agent(self, agent_id: str, agent_type: AgentType, agent_instance: Any):
        """注册Agent"""
        
        self.agents[agent_id] = {
            "type": agent_type,
            "instance": agent_instance,
            "status": "active"
        }
        
        # 订阅相关消息
        message_types = self._get_agent_message_types(agent_type)
        self.collaboration_bus.subscribe(agent_id, message_types)
        
        # 订阅共享数据
        data_keys = self._get_agent_data_keys(agent_type)
        for key in data_keys:
            self.data_sharing.subscribe_to_data(key, agent_id, self._handle_data_update)
        
        logger.info(f"Agent {agent_id} registered as {agent_type}")
    
    def execute_task(self, task: Task) -> str:
        """执行任务"""
        
        task_id = task.id
        
        # 添加到任务队列
        self.task_queue.add_task(task)
        
        # 监控任务开始
        self.monitoring.record_metric("task_started", 1, {"task_id": task_id})
        
        logger.info(f"Task {task_id} queued for execution")
        return task_id
    
    def _start_task_processor(self):
        """启动任务处理器"""
        
        def process_tasks():
            while self.running:
                try:
                    # 获取下一个任务
                    task = self.task_queue.get_next_task()
                    
                    if task:
                        # 执行任务
                        self._execute_task(task)
                    
                    time.sleep(0.1)  # 避免CPU过度占用
                    
                except Exception as e:
                    logger.error(f"Error in task processor: {e}")
        
        processor_thread = threading.Thread(target=process_tasks)
        processor_thread.daemon = True
        processor_thread.start()
    
    def _execute_task(self, task: Task):
        """执行单个任务"""
        
        task_id = task.id
        agent_instance = self.agents.get(task.agent_type.value, {}).get("instance")
        
        if not agent_instance:
            error_msg = f"No agent found for type: {task.agent_type}"
            self.task_queue.complete_task(task_id, error=error_msg)
            return
        
        try:
            # 监控任务执行时间
            start_time = time.time()
            
            # 执行任务
            result = agent_instance.execute_task(task.data)
            
            # 记录执行时间
            execution_time = time.time() - start_time
            self.monitoring.record_metric("task_completion_time", execution_time, {
                "task_id": task_id,
                "agent_type": task.agent_type.value
            })
            
            # 完成任务
            self.task_queue.complete_task(task_id, result=result)
            
            # 发布任务完成消息
            self.collaboration_bus.publish(AgentMessage(
                id=str(uuid.uuid4()),
                from_agent="system",
                to_agent="all",
                message_type="task_completed",
                content={
                    "task_id": task_id,
                    "result": result,
                    "execution_time": execution_time
                },
                timestamp=datetime.now()
            ))
            
        except Exception as e:
            error_msg = f"Task execution failed: {str(e)}"
            self.monitoring.record_metric("task_error", 1, {
                "task_id": task_id,
                "error": error_msg
            })
            
            # 完成任务（失败）
            self.task_queue.complete_task(task_id, error=error_msg)
            
            # 重试逻辑
            if task.retry_count < task.max_retries:
                self.task_queue.retry_task(task_id)
            else:
                logger.error(f"Task {task_id} failed permanently: {error_msg}")
    
    def _handle_task_result(self, message: AgentMessage):
        """处理任务结果消息"""
        
        task_id = message.content.get("task_id")
        result = message.content.get("result")
        error = message.content.get("error")
        
        if task_id:
            if error:
                self.task_queue.complete_task(task_id, error=error)
            else:
                self.task_queue.complete_task(task_id, result=result)
    
    def _handle_data_request(self, message: AgentMessage):
        """处理数据请求消息"""
        
        key = message.content.get("key")
        requesting_agent = message.from_agent
        
        if key:
            data = self.data_sharing.get_data(key, requesting_agent)
            
            # 发送回复
            reply = AgentMessage(
                id=str(uuid.uuid4()),
                from_agent="system",
                to_agent=requesting_agent,
                message_type="data_response",
                content={"key": key, "data": data},
                timestamp=datetime.now(),
                correlation_id=message.id
            )
            
            self.collaboration_bus.publish(reply)
    
    def _handle_data_update(self, event_type: str, data: Any, key: str):
        """处理数据更新"""
        
        # 发布数据更新消息
        self.collaboration_bus.publish(AgentMessage(
            id=str(uuid.uuid4()),
            from_agent="system",
            to_agent="all",
            message_type="data_updated",
            content={"key": key, "data": data, "event": event_type},
            timestamp=datetime.now()
        ))
    
    def _handle_decision_request(self, message: AgentMessage):
        """处理决策请求消息"""
        
        decisions = message.content.get("decisions", [])
        strategy = message.content.get("strategy", "confidence_based")
        requesting_agent = message.from_agent
        
        if decisions:
            # 融合决策
            fused_decision = self.decision_fusion.fuse_decisions(decisions, strategy)
            
            # 发送回复
            reply = AgentMessage(
                id=str(uuid.uuid4()),
                from_agent="system",
                to_agent=requesting_agent,
                message_type="decision_response",
                content={"fused_decision": fused_decision, "strategy": strategy},
                timestamp=datetime.now(),
                correlation_id=message.id
            )
            
            self.collaboration_bus.publish(reply)
    
    def _get_agent_message_types(self, agent_type: AgentType) -> List[str]:
        """获取Agent的消息类型"""
        
        message_types = {
            AgentType.CLIMATE: ["data_request", "task_result", "decision_request"],
            AgentType.CROP: ["data_request", "task_result", "decision_request"],
            AgentType.GROWTH: ["data_request", "task_result", "decision_request"],
            AgentType.ECO: ["data_request", "task_result", "decision_request"],
            AgentType.MARKET: ["data_request", "task_result", "decision_request"],
            AgentType.FINANCE: ["data_request", "task_result", "decision_request"],
            AgentType.RISK: ["data_request", "task_result", "decision_request"],
            AgentType.PEST: ["data_request", "task_result", "decision_request"],
            AgentType.NUTRITION: ["data_request", "task_result", "decision_request"],
            AgentType.SEASON: ["data_request", "task_result", "decision_request"],
            AgentType.SOIL: ["data_request", "task_result", "decision_request"]
        }
        
        return message_types.get(agent_type, ["data_request", "task_result"])
    
    def _get_agent_data_keys(self, agent_type: AgentType) -> List[str]:
        """获取Agent的数据键"""
        
        data_keys = {
            AgentType.CLIMATE: ["climate_data", "weather_forecast"],
            AgentType.CROP: ["crop_data", "crop_database"],
            AgentType.GROWTH: ["growth_data", "growth_models"],
            AgentType.ECO: ["eco_data", "environmental_factors"],
            AgentType.MARKET: ["market_data", "price_history"],
            AgentType.FINANCE: ["finance_data", "economic_indicators"],
            AgentType.RISK: ["risk_data", "risk_assessments"],
            AgentType.PEST: ["pest_data", "disease_database"],
            AgentType.NUTRITION: ["nutrition_data", "soil_fertility"],
            AgentType.SEASON: ["season_data", "planting_calendar"],
            AgentType.SOIL: ["soil_data", "soil_properties"]
        }
        
        return data_keys.get(agent_type, ["shared_data"])
    
    def get_system_status(self) -> Dict:
        """获取系统状态"""
        
        return {
            "running": self.running,
            "agents_count": len(self.agents),
            "active_agents": sum(1 for agent in self.agents.values() if agent["status"] == "active"),
            "pending_tasks": len([t for t in self.task_queue.tasks.values() if t.status == TaskStatus.PENDING]),
            "running_tasks": len(self.task_queue.running_tasks),
            "completed_tasks": len(self.task_queue.completed_tasks),
            "alerts_count": len(self.monitoring.alerts),
            "health_status": self.monitoring.get_health_status()
        }
    
    def get_collaboration_insights(self) -> Dict:
        """获取协作洞察"""
        
        return {
            "task_efficiency": self._calculate_task_efficiency(),
            "data_access_patterns": self._analyze_data_access_patterns(),
            "decision_quality": self._analyze_decision_quality(),
            "agent_performance": self._analyze_agent_performance()
        }
    
    def _calculate_task_efficiency(self) -> Dict:
        """计算任务效率"""
        
        completed_tasks = [t for t in self.task_queue.completed_tasks if t.status == TaskStatus.COMPLETED]
        
        if not completed_tasks:
            return {"efficiency": 0.0, "avg_completion_time": 0.0}
        
        total_time = sum((t.completed_at - t.started_at).total_seconds() for t in completed_tasks if t.started_at and t.completed_at)
        avg_time = total_time / len(completed_tasks) if completed_tasks else 0.0
        
        success_rate = len([t for t in completed_tasks if t.status == TaskStatus.COMPLETED]) / len(completed_tasks)
        
        return {
            "efficiency": success_rate,
            "avg_completion_time": avg_time,
            "total_completed": len(completed_tasks)
        }
    
    def _analyze_data_access_patterns(self) -> Dict:
        """分析数据访问模式"""
        
        # 简化的数据访问分析
        access_patterns = {}
        
        for key, data_info in self.data_sharing.shared_data.items():
            access_count = len([entry for entry in self.data_sharing.shared_data.values() if entry["data"] == data_info["data"]])
            access_patterns[key] = {
                "access_count": access_count,
                "last_access": data_info["timestamp"],
                "data_size": len(str(data_info["data"]))
            }
        
        return access_patterns
    
    def _analyze_decision_quality(self) -> Dict:
        """分析决策质量"""
        
        if not self.decision_fusion.decision_history:
            return {"quality_score": 0.0, "total_decisions": 0}
        
        total_decisions = len(self.decision_fusion.decision_history)
        avg_confidence = sum(entry["confidence"] for entry in self.decision_fusion.decision_history) / total_decisions
        
        return {
            "quality_score": avg_confidence,
            "total_decisions": total_decisions,
            "strategy_usage": self._analyze_strategy_usage()
        }
    
    def _analyze_strategy_usage(self) -> Dict:
        """分析策略使用情况"""
        
        strategy_counts = {}
        for entry in self.decision_fusion.decision_history:
            strategy = entry["strategy"]
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        
        return strategy_counts
    
    def _analyze_agent_performance(self) -> Dict:
        """分析Agent性能"""
        
        performance = {}
        
        for agent_id, agent_info in self.agents.items():
            if agent_info["status"] == "active":
                # 获取Agent的健康状态
                health = self.monitoring.get_health_status(agent_id)
                
                # 计算Agent的任务完成情况
                agent_tasks = [t for t in self.task_queue.completed_tasks if t.agent_type.value == agent_id]
                completed_count = len([t for t in agent_tasks if t.status == TaskStatus.COMPLETED])
                failed_count = len([t for t in agent_tasks if t.status == TaskStatus.FAILED])
                
                performance[agent_id] = {
                    "status": agent_info["status"],
                    "health": health,
                    "completed_tasks": completed_count,
                    "failed_tasks": failed_count,
                    "success_rate": completed_count / (completed_count + failed_count) if (completed_count + failed_count) > 0 else 0.0
                }
        
        return performance