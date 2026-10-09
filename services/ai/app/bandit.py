"""
Contextual Bandit Service Module
Implements ε-greedy exploration for 8-action policy learning.
"""

import logging
import numpy as np
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
import json

from app import config

logger = logging.getLogger(__name__)

# ============================================================
# BANDIT SERVICE
# ============================================================

@dataclass
class ActionStats:
    """Statistics for a single action."""
    count: int = 0
    total_reward: float = 0.0
    mean_reward: float = 0.0
    
    def update(self, reward: float) -> None:
        """Update action statistics with new reward."""
        self.count += 1
        self.total_reward += reward
        self.mean_reward = self.total_reward / self.count


class ContextualBandit:
    """
    8-Action Contextual Bandit using ε-greedy exploration.
    Learns optimal actions based on state vectors.
    """
    
    def __init__(self, state_dim: int = 8, num_actions: int = 8):
        """
        Initialize bandit.
        
        Args:
            state_dim: State vector dimensionality (8D)
            num_actions: Number of actions (8)
        """
        self.state_dim = state_dim
        self.num_actions = num_actions
        self.epsilon = config.BANDIT_EPSILON
        self.actions = config.BANDIT_ACTIONS
        
        # Action statistics for learning
        self.action_stats: dict[int, ActionStats] = {
            i: ActionStats() for i in range(num_actions)
        }
        
        logger.info(
            f"✅ Contextual Bandit initialized: "
            f"{num_actions} actions, ε={self.epsilon}, state_dim={state_dim}"
        )
    
    def select_action(self, state: np.ndarray) -> int:
        """
        Select action using ε-greedy exploration.
        
        Args:
            state: 8D state vector [correctness, response_time, difficulty, 
                                    topic_match, engagement, question_count, 
                                    error_rate, time_spent]
        
        Returns:
            Selected action index (0-7)
        """
        if len(state) != self.state_dim:
            raise ValueError(
                f"State dimension mismatch: expected {self.state_dim}, got {len(state)}"
            )
        
        # ε-greedy: explore with probability ε, exploit with probability 1-ε
        if np.random.random() < self.epsilon:
            action = np.random.randint(0, self.num_actions)
            logger.debug(f"Exploration: selected action {action} ({self.actions[action]})")
        else:
            action = self._select_best_action()
            logger.debug(f"Exploitation: selected action {action} ({self.actions[action]})")
        
        return action
    
    def _select_best_action(self) -> int:
        """
        Select best action based on empirical rewards.
        Ties broken randomly.
        
        Returns:
            Action index with highest mean reward
        """
        mean_rewards = [
            stats.mean_reward if stats.count > 0 else 0.0
            for stats in self.action_stats.values()
        ]
        
        # Handle unvisited actions (ucb-style bonus)
        for i, stats in self.action_stats.items():
            if stats.count == 0:
                mean_rewards[i] = float('inf')  # Prefer unvisited
        
        # Find best action (with tie-breaking)
        best_reward = max(mean_rewards)
        best_actions = [i for i, r in enumerate(mean_rewards) if r == best_reward]
        
        return np.random.choice(best_actions)
    
    async def update(self, action: int, reward: float) -> None:
        """
        Update bandit with observed reward (async for Redis compatibility).
        
        Args:
            action: Action taken
            reward: Observed reward
        """
        if action < 0 or action >= self.num_actions:
            raise ValueError(f"Invalid action: {action}")
        
        if reward < 0 or reward > 1:
            logger.warning(f"Reward outside [0,1]: {reward}")
            reward = np.clip(reward, 0, 1)
        
        self.action_stats[action].update(reward)
        
        logger.debug(
            f"Action {action} ({self.actions[action]}): "
            f"reward={reward:.3f}, count={self.action_stats[action].count}, "
            f"mean={self.action_stats[action].mean_reward:.3f}"
        )
    
    def get_statistics(self) -> dict:
        """
        Get current bandit statistics for logging/analysis.
        
        Returns:
            Statistics for all actions
        """
        stats = {}
        for i, action_name in enumerate(self.actions):
            stats[action_name] = {
                "count": self.action_stats[i].count,
                "mean_reward": float(self.action_stats[i].mean_reward),
                "total_reward": float(self.action_stats[i].total_reward)
            }
        return stats
    
    def recommend_action_by_state(
        self,
        state: np.ndarray,
        learner_level: int = 2
    ) -> tuple[int, str]:
        """
        Recommend action based on state and learner level.
        
        Args:
            state: 8D state vector
            learner_level: Learner detail level (1-3)
            
        Returns:
            (action_id, action_name)
        """
        action = self.select_action(state)
        return action, self.actions[action]


# Global bandit instance
bandit = ContextualBandit(
    state_dim=config.BANDIT_STATE_DIM,
    num_actions=config.BANDIT_NUM_ACTIONS
)
