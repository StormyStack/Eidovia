#!/usr/bin/env python3
"""
Contextual Bandit with PostgreSQL Logging
Thompson Sampling + Database persistence for thesis
"""

import numpy as np
import logging
from typing import Dict
from uuid import UUID

logger = logging.getLogger(__name__)

class ContextualBandit:
    """Thompson Sampling Bandit with PostgreSQL logging"""
    
    def __init__(self, db, state_dim: int = 8, num_actions: int = 8):
        self.db = db
        self.state_dim = state_dim
        self.num_actions = num_actions
        
        # Thompson Sampling posteriors
        self.alpha = np.ones(num_actions)
        self.beta = np.ones(num_actions)
        
        self.action_names = [
            "difficulty_easy", "difficulty_medium", "difficulty_hard",
            "topic_structure", "topic_replication", 
            "topic_transcription", "topic_translation", "topic_mutations"
        ]
    
    def select_action(self, state: np.ndarray) -> int:
        """Thompson Sampling: select action"""
        sampled_rewards = np.random.beta(self.alpha, self.beta)
        action = np.argmax(sampled_rewards)
        return int(action)
    
    async def update(self, action: int, reward: float):
        """Update posterior distribution + log to database"""
        if reward > 0.5:
            self.alpha[action] += 1
        else:
            self.beta[action] += 1
        
        logger.debug(f"Updated action {action} (reward={reward:.2f})")
    
    async def log_decision(self, 
                          user_id: UUID,
                          session_id: UUID,
                          question: str,
                          is_on_topic: bool,
                          topic_similarity: float,
                          retrieved_chunks: int,
                          llm_response: str,
                          latency_ms: float,
                          action_id: int,
                          recommended_difficulty: int,
                          recommended_topic: str,
                          reward: float = 0.0):
        """Log AI decision to database"""
        try:
            decision_data = {
                'user_id': user_id,
                'session_id': session_id,
                'question': question,
                'is_on_topic': is_on_topic,
                'topic_similarity': topic_similarity,
                'retrieved_chunks': retrieved_chunks,
                'llm_response': llm_response,
                'latency_ms': latency_ms,
                'action_id': action_id,
                'action_name': self.action_names[action_id],
                'recommended_difficulty': recommended_difficulty,
                'recommended_topic': recommended_topic,
                'reward': reward
            }
            
            decision_id = await self.db.log_decision(decision_data)
            logger.info(f"Decision logged: {decision_id}")
            return decision_id
        except Exception as e:
            logger.error(f"Failed to log decision: {e}")
            return None
    
    async def log_episode(self,
                         user_id: UUID,
                         session_id: UUID,
                         state_vector: list,
                         action_id: int,
                         reward: float,
                         next_state_vector: list = None,
                         done: bool = False):
        """Log RL episode to database"""
        try:
            episode_data = {
                'user_id': user_id,
                'session_id': session_id,
                'state_vector': state_vector,
                'action_id': action_id,
                'reward': reward,
                'next_state_vector': next_state_vector,
                'done': done
            }
            
            episode_id = await self.db.log_episode(episode_data)
            logger.info(f"Episode logged: {episode_id}")
            return episode_id
        except Exception as e:
            logger.error(f"Failed to log episode: {e}")
            return None
    
    def get_statistics(self) -> Dict:
        """Get bandit statistics for analysis"""
        avg_rewards = self.alpha / (self.alpha + self.beta)
        return {
            'action_counts': (self.alpha + self.beta - 2).tolist(),
            'avg_rewards': avg_rewards.tolist(),
            'posterior_alpha': self.alpha.tolist(),
            'posterior_beta': self.beta.tolist()
        }

# Global bandit instance
bandit = None

async def get_bandit():
    """Get or create bandit instance"""
    global bandit
    if bandit is None:
        bandit = ContextualBandit(db=None)  # Initialize with db later
    return bandit
