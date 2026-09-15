#!/usr/bin/env python3
"""
Week 4 Metrics Analysis
Analyze pilot study results and generate thesis-ready metrics
"""

import json
import numpy as np
from collections import defaultdict

def analyze_pilot_study():
    """Analyze pilot study data from data/sessions.json"""
    
    # Load pilot study data
    with open('data/sessions.json', 'r') as f:
        data = json.load(f)
    
    sessions = data['sessions']
    
    print("=" * 70)
    print("📊 WEEK 4: PILOT STUDY ANALYSIS")
    print("=" * 70)
    
    # Aggregate by user
    user_data = defaultdict(list)
    for session in sessions:
        user_name = session['user_name']
        accuracy = session['accuracy']
        user_data[user_name].append(accuracy)
    
    print("\n[Learning Curves - Accuracy by Session]\n")
    
    overall_accuracies = []
    for user_name in sorted(user_data.keys()):
        accuracies = user_data[user_name]
        overall_accuracies.extend(accuracies)
        
        improvement = accuracies[-1] - accuracies[0]
        print(f"{user_name:25} | Sessions: {accuracies}")
        print(f"{'':25} | Improvement: {improvement:+.1%} (Session 1→5)")
        print()
    
    # Overall metrics
    print("\n[Overall Metrics]\n")
    
    total_interactions = sum(len(s['interactions']) for s in sessions)
    total_questions = len(sessions) * 10  # 10 questions per session
    total_correct = sum(s['questions_correct'] for s in sessions)
    overall_accuracy = total_correct / total_questions
    
    print(f"Total sessions: {len(sessions)}")
    print(f"Total interactions: {total_interactions}")
    print(f"Overall accuracy: {overall_accuracy:.1%}")
    print(f"Average session accuracy: {np.mean(overall_accuracies):.1%}")
    print(f"Accuracy std dev: {np.std(overall_accuracies):.1%}")
    
    # Adaptation effectiveness
    print("\n[Bandit Adaptation Analysis]\n")
    
    bandit_stats = data['bandit_stats']
    action_counts = bandit_stats['action_counts']
    avg_rewards = bandit_stats['avg_rewards']
    
    action_names = [
        "Difficulty: Easy", "Difficulty: Medium", "Difficulty: Hard",
        "Topic: DNA Structure", "Topic: DNA Replication", 
        "Topic: Transcription", "Topic: Translation", "Topic: Mutations"
    ]
    
    print("Action Performance (Thompson Sampling Outcomes):")
    for i, (name, count, reward) in enumerate(zip(action_names, action_counts, avg_rewards)):
        if count > 0:
            print(f"  {i}: {name:30} | Count: {int(count):3} | Avg Reward: {reward:.2%}")
    
    # Most effective actions
    top_actions = np.argsort(avg_rewards)[::-1][:3]
    print(f"\nTop 3 most effective actions:")
    for rank, action_id in enumerate(top_actions, 1):
        print(f"  {rank}. {action_names[action_id]} (reward: {avg_rewards[action_id]:.2%})")
    
    # Exploration efficiency
    exploration = np.where(np.array(action_counts) > 0)[0]
    print(f"\nBandit explored {len(exploration)}/8 actions (exploration efficiency)")
    
    # Save analysis
    analysis = {
        "total_sessions": len(sessions),
        "total_interactions": total_interactions,
        "overall_accuracy": float(overall_accuracy),
        "average_session_accuracy": float(np.mean(overall_accuracies)),
        "learning_curves": {user: accuracies for user, accuracies in user_data.items()},
        "bandit_action_counts": action_counts,
        "bandit_avg_rewards": [float(r) for r in avg_rewards],
        "exploration_rate": float(len(exploration) / 8),
    }
    
    with open('data/pilot_study_analysis.json', 'w') as f:
        json.dump(analysis, f, indent=2)
    
    print("\n✅ Analysis saved to data/pilot_study_analysis.json\n")
    print("=" * 70)
    
    return analysis

if __name__ == "__main__":
    analyze_pilot_study()
