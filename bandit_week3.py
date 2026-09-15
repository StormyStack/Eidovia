#!/usr/bin/env python3
"""
Contextual Bandit for Personalized Learning
Uses Thompson Sampling for exploration/exploitation trade-off
"""

import numpy as np
import logging
from typing import Dict, List, Tuple

from config_week3 import (
    STATE_DIMENSION,
    NUM_ACTIONS,
    THOMPSON_ALPHA,
    THOMPSON_BETA,
    THOMPSON_LAMBDA,
    STATE_FEATURES,
    ACTIONS,
)

logger = logging.getLogger("bandit")

class ContextualBandit:
    """
    Thompson Sampling Bandit for personalized learning.
    
    State: 8D vector (accuracy, response_time, difficulty, topic_match, engagement, question_count, error_rate, time_spent)
    Actions: 8 (3 difficulty levels + 5 topic choices)
    Reward: Learning outcome (accuracy improvement)
    """
    
    def __init__(self):
        self.state_dim = STATE_DIMENSION
        self.num_actions = NUM_ACTIONS
        
        # Thompson Sampling: maintain posterior distribution for each action
        # Each action has α (successes) and β (failures)
        self.alpha = np.ones(self.num_actions) * THOMPSON_ALPHA
        self.beta = np.ones(self.num_actions) * THOMPSON_BETA
        
        # Action statistics
        self.action_counts = np.zeros(self.num_actions)
        self.action_rewards = np.zeros(self.num_actions)
        self.action_rewards_sq = np.zeros(self.num_actions)
        
        logger.info(f"✅ Bandit initialized: {self.state_dim}D state, {self.num_actions} actions")
    
    def select_action(self, state: np.ndarray) -> int:
        """
        Thompson Sampling: sample from posterior, pick action with highest reward.
        
        Args:
            state: 8D state vector
        
        Returns:
            action_id (0-7)
        """
        if not isinstance(state, np.ndarray):
            state = np.array(state, dtype=np.float32)
        
        # Sample from Beta posterior for each action
        # This naturally balances exploration (uncertain actions) vs exploitation (proven actions)
        sampled_rewards = np.random.beta(self.alpha, self.beta)
        
        # Weight by state relevance (simple: state dot product)
        state_normalized = (state - np.mean(state)) / (np.std(state) + 1e-8)
        relevance = np.abs(state_normalized[:self.num_actions]) if len(state) >= self.num_actions else np.ones(self.num_actions)
        
        weighted_rewards = sampled_rewards * relevance
        
        action = np.argmax(weighted_rewards)
        
        return int(action)
    
    def update(self, action: int, reward: float):
        """
        Update posterior distribution based on outcome.
        
        Args:
            action: Selected action (0-7)
            reward: Outcome (0=fail, 1=success)
        """
        # Update Beta distribution
        if reward > 0.5:
            self.alpha[action] += 1
        else:
            self.beta[action] += 1
        
        # Track statistics
        self.action_counts[action] += 1
        self.action_rewards[action] += reward
        self.action_rewards_sq[action] += reward ** 2
        
        logger.debug(f"Updated action {action} (reward={reward:.2f})")
    
    def get_action_info(self, action_id: int) -> Dict:
        """Get information about an action"""
        return ACTIONS.get(action_id, {})
    
    def get_statistics(self) -> Dict:
        """Get bandit statistics for logging/analysis"""
        avg_rewards = self.action_rewards / (self.action_counts + 1e-8)
        var_rewards = (
            self.action_rewards_sq / (self.action_counts + 1e-8) - avg_rewards ** 2
        )
        
        return {
            "action_counts": self.action_counts.tolist(),
            "avg_rewards": avg_rewards.tolist(),
            "variance": var_rewards.tolist(),
            "posterior_alpha": self.alpha.tolist(),
            "posterior_beta": self.beta.tolist(),
        }

class UserState:
    """Maintains user state vector (8D)"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.state = np.ones(STATE_DIMENSION, dtype=np.float32) * 0.5  # Initialize to neutral
        
        self.questions_answered = 0
        self.correct_answers = 0
        self.recent_accuracy_window = []
        self.total_time_ms = 0
        
        self.current_difficulty = 1  # medium
        self.current_topic = "DNA Structure"
        self.engagement_streak = 0
        
        logger.debug(f"Created state for user {user_id}")
    
    def update_from_interaction(
        self,
        correct: bool,
        response_time_ms: float,
        difficulty: int,
        topic: str,
    ):
        """
        Update state based on user interaction.
        
        Args:
            correct: Did user answer correctly?
            response_time_ms: How long did it take?
            difficulty: Question difficulty (0=easy, 1=medium, 2=hard)
            topic: Question topic
        """
        self.questions_answered += 1
        if correct:
            self.correct_answers += 1
            self.engagement_streak += 1
        else:
            self.engagement_streak = 0
        
        self.recent_accuracy_window.append(1.0 if correct else 0.0)
        if len(self.recent_accuracy_window) > 10:
            self.recent_accuracy_window.pop(0)
        
        self.total_time_ms += response_time_ms
        self.current_difficulty = difficulty
        self.current_topic = topic
        
        # Update state vector
        self._compute_state()
    
    def _compute_state(self) -> np.ndarray:
        """Compute 8D state vector from interactions"""
        # Feature 0: Accuracy (0-1)
        accuracy = (
            np.mean(self.recent_accuracy_window)
            if self.recent_accuracy_window
            else 0.5
        )
        
        # Feature 1: Response time (normalized, 0-1)
        avg_time = self.total_time_ms / max(self.questions_answered, 1)
        response_time_norm = min(avg_time / 5000, 1.0)  # 5s is max
        
        # Feature 2: Difficulty level (0-1)
        difficulty_norm = self.current_difficulty / 2.0
        
        # Feature 3: Topic match (mock: 0.8 if focused, 0.5 if varied)
        topic_match = 0.8 if self.engagement_streak > 2 else 0.5
        
        # Feature 4: Engagement (0-1, based on streak)
        engagement = min(self.engagement_streak / 5.0, 1.0)
        
        # Feature 5: Question count (normalized, 0-1)
        question_norm = min(self.questions_answered / 50.0, 1.0)
        
        # Feature 6: Error rate (0-1)
        error_rate = 1.0 - accuracy
        
        # Feature 7: Time spent (normalized, 0-1)
        time_norm = min(self.total_time_ms / 600000, 1.0)  # 10 minutes max
        
        self.state = np.array(
            [
                accuracy,
                response_time_norm,
                difficulty_norm,
                topic_match,
                engagement,
                question_norm,
                error_rate,
                time_norm,
            ],
            dtype=np.float32,
        )
        
        return self.state
    
    def get_state(self) -> np.ndarray:
        """Get current state vector"""
        return self.state.copy()
    
    def to_dict(self) -> Dict:
        """Serialize state for logging"""
        return {
            "user_id": self.user_id,
            "questions_answered": self.questions_answered,
            "correct_answers": self.correct_answers,
            "accuracy": self.correct_answers / max(self.questions_answered, 1),
            "current_difficulty": self.current_difficulty,
            "current_topic": self.current_topic,
            "engagement_streak": self.engagement_streak,
            "state_vector": self.state.tolist(),
        }

# Global bandit instance
_bandit_instance = None
_user_states = {}

def get_bandit() -> ContextualBandit:
    """Get or create global bandit"""
    global _bandit_instance
    if _bandit_instance is None:
        _bandit_instance = ContextualBandit()
    return _bandit_instance

def get_user_state(user_id: str) -> UserState:
    """Get or create user state"""
    if user_id not in _user_states:
        _user_states[user_id] = UserState(user_id)
    return _user_states[user_id]
