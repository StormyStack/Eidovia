#!/usr/bin/env python3
"""
Mock User Simulator for Pilot Study
Generates realistic learner trajectories with personalized preferences
"""

import json
import logging
import numpy as np
from datetime import datetime
from typing import List, Dict

from config_week3 import (
    MOCK_USERS,
    QUESTIONS_PER_SESSION,
    NUM_SIMULATION_SESSIONS,
    SESSIONS_FILE,
    ACTIONS,
)
from bandit_week3 import ContextualBandit, UserState

logger = logging.getLogger("simulator")

# JSON Encoder for numpy types
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.bool_, np.integer, np.floating)):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

class MockUser:
    """Simulated learner with preferences and learning curve"""
    
    def __init__(self, config: Dict):
        self.user_id = config["user_id"]
        self.name = config["name"]
        self.difficulty_preference = config["difficulty_preference"]
        self.topic_preference = config["topic_preference"]
        self.learning_rate = config["learning_rate"]
        self.engagement = config["engagement"]
        
        self.baseline_accuracy = 0.4 + np.random.normal(0, 0.1)
        self.baseline_accuracy = np.clip(self.baseline_accuracy, 0.2, 0.8)
        
        self.state = UserState(self.user_id)
    
    def answer_question(
        self,
        question_difficulty: int,
        question_topic: str,
        bandit_action: int,
    ) -> Dict:
        """Simulate answering a question."""
        
        difficulty_match = 1.0 - abs(question_difficulty - self.difficulty_preference) * 0.3
        topic_match = 1.0 if question_topic == self.topic_preference else 0.7
        difficulty_penalty = 0.2 * question_difficulty
        
        probability_correct = (
            self.baseline_accuracy
            * difficulty_match
            * topic_match
            * (1.0 - difficulty_penalty)
        )
        probability_correct = np.clip(probability_correct, 0.1, 0.95)
        
        correct = np.random.random() < probability_correct
        
        # Response time
        base_time = 3000 + np.random.normal(0, 500)
        base_time += question_difficulty * 1000
        base_time = max(base_time, 1000)
        
        # Update state
        self.state.update_from_interaction(
            correct=correct,
            response_time_ms=base_time,
            difficulty=question_difficulty,
            topic=question_topic,
        )
        
        # Improve baseline
        if correct:
            self.baseline_accuracy += self.learning_rate * 0.01
            self.baseline_accuracy = min(self.baseline_accuracy, 0.95)
        
        reward = 1.0 if correct else 0.0
        
        return {
            "correct": correct,
            "response_time_ms": base_time,
            "accuracy": probability_correct,
            "reward": reward,
        }

def run_simulation() -> Dict:
    """Run full pilot study simulation."""
    logger.info("=" * 70)
    logger.info("🎓 WEEK 3: PILOT STUDY - SIMULATED LEARNERS")
    logger.info("=" * 70)
    
    bandit = ContextualBandit()
    all_sessions = []
    
    for user_config in MOCK_USERS:
        logger.info(f"\n[User: {user_config['name']}]")
        mock_user = MockUser(user_config)
        
        for session_num in range(NUM_SIMULATION_SESSIONS):
            session_data = {
                "session_id": f"{mock_user.user_id}_session_{session_num}",
                "user_id": mock_user.user_id,
                "user_name": mock_user.name,
                "session_num": session_num + 1,
                "timestamp": datetime.now().isoformat(),
                "interactions": [],
            }
            
            total_correct = 0
            
            for q_num in range(QUESTIONS_PER_SESSION):
                # Get current state
                state = mock_user.state.get_state()
                
                # Bandit selects action
                action = bandit.select_action(state)
                action_info = ACTIONS[action]
                
                # Extract difficulty and topic from action
                if action < 3:
                    difficulty = action
                    topic = mock_user.topic_preference
                else:
                    difficulty = mock_user.difficulty_preference
                    topic = action_info.get("topic", "DNA Structure")
                
                # Mock user answers
                result = mock_user.answer_question(difficulty, topic, action)
                
                # Update bandit
                bandit.update(action, result["reward"])
                
                if result["correct"]:
                    total_correct += 1
                
                # Record interaction
                session_data["interactions"].append({
                    "question_num": q_num + 1,
                    "action": action,
                    "action_name": action_info["name"],
                    "difficulty": difficulty,
                    "topic": topic,
                    "correct": result["correct"],
                    "response_time_ms": float(result["response_time_ms"]),
                    "user_state": mock_user.state.to_dict(),
                })
            
            # Compute session metrics
            accuracy = total_correct / QUESTIONS_PER_SESSION
            session_data["accuracy"] = accuracy
            session_data["questions_correct"] = total_correct
            
            all_sessions.append(session_data)
            
            logger.info(
                f"  Session {session_num + 1}: Accuracy {accuracy:.1%} "
                f"({total_correct}/{QUESTIONS_PER_SESSION})"
            )
    
    # Save results
    logger.info(f"\n[Saving Results]")
    results = {
        "simulation_date": datetime.now().isoformat(),
        "config": {
            "num_users": len(MOCK_USERS),
            "questions_per_session": QUESTIONS_PER_SESSION,
            "sessions_per_user": NUM_SIMULATION_SESSIONS,
        },
        "sessions": all_sessions,
        "bandit_stats": bandit.get_statistics(),
    }
    
    with open(SESSIONS_FILE, 'w') as f:
        json.dump(results, f, indent=2, cls=NumpyEncoder)
    
    logger.info(f"✅ Saved {len(all_sessions)} sessions to {SESSIONS_FILE}")
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("✅ PILOT STUDY COMPLETE")
    logger.info("=" * 70)
    
    total_questions = len(MOCK_USERS) * NUM_SIMULATION_SESSIONS * QUESTIONS_PER_SESSION
    total_correct = sum(s["questions_correct"] for s in all_sessions)
    overall_accuracy = total_correct / total_questions
    
    logger.info(f"Total interactions: {total_questions}")
    logger.info(f"Overall accuracy: {overall_accuracy:.1%}")
    logger.info(f"Bandit adaptation: {bandit.get_statistics()}")
    logger.info("=" * 70 + "\n")
    
    return results

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_simulation()