# LinupOSAI - Learning System Integration Guide

## Overview

The learning system enables Linup to adapt to YOUR betting style and learn from your decisions. It tracks every decision you make, analyzes what works and what doesn't, and provides increasingly personalized recommendations.

## Architecture

### 4 New Core Modules

1. **ai_decision_tracker.py** - Records every decision and outcome
2. **ai_learning_engine.py** - Learns from your decisions
3. **ai_adaptive_recommender.py** - Gives personalized suggestions
4. **ai_learning_demo.py** - Example usage

### Key Concepts

**Decision**: A bet you make (what, when, why, outcome)
**Pattern**: A recurring successful or unsuccessful decision type
**Profile**: Your complete betting style and preferences
**Adaptation**: System adjusts recommendations based on your history

## Database Schema Addition

```sql
-- Track every decision
decisions (decision_id, session_id, spin_number, bet_target, bet_type, 
           bet_amount, decision_context, source, decision_time, 
           spin_result, outcome, profit_loss, player_satisfaction, notes)

-- Explicit feedback
decision_feedback (feedback_id, decision_id, rating, comment, feedback_time)

-- Learned patterns
learned_patterns (pattern_id, player_pattern_key, context_hash, 
                 decision_feature_set, win_count, loss_count, 
                 average_profit, confidence, last_used, created_at)
```

## Integration Steps

### 1. Initialize Learning System

```python
from ai_decision_tracker import DecisionTracker, Decision
from ai_learning_engine import LearningEngine
from ai_adaptive_recommender import AdaptiveRecommender

# In your app initialization:
decision_tracker = DecisionTracker()
learning_engine = LearningEngine(decision_tracker)
adaptive_recommender = AdaptiveRecommender(
    base_recommender,      # Your existing RecommendationEngine
    learning_engine,
    decision_tracker
)
```

### 2. Record Decisions

After the player makes a bet:

```python
decision = Decision(
    decision_id=f"dec_{session_id}_{spin_number}",
    session_id=session_id,
    spin_number=spin_number,
    bet_target="34",           # What they bet on
    bet_type="group",          # group or number
    bet_amount=10,
    decision_context={
        'confidence': 0.75,    # How confident they were
        'reason': 'Group clustering detected',
        'patterns_detected': 3
    },
    source="manual",           # 'manual' or 'ai_recommendation'
    decision_time=datetime.now(),
    spin_result=None,          # Will be filled after spin
    outcome="pending",
    profit_loss=None,
    player_satisfaction=None
)

decision_tracker.record_decision(decision)
```

### 3. Update with Outcome

After the spin result is known:

```python
decision_tracker.record_outcome(
    decision_id="dec_001",
    spin_result=14,
    outcome="win",  # or "loss", "break_even"
    profit_loss=10  # The actual profit/loss
)
```

### 4. Get Personalized Recommendations

Instead of using base recommendations:

```python
# Before (base recommendations):
recommendations = recommender.generate_spin_recommendations(recent_spins)

# After (personalized):
personalized_recs = adaptive_recommender.get_personalized_recommendations(recent_spins)

# Much better! Now includes:
# - Boosts for your best targets
# - Your historical win rate with each bet
# - Warnings for bets you struggle with
```

### 5. Request Player Feedback

After a decision outcome:

```python
# Optional: Get player feedback on the decision
decision_tracker.add_feedback(
    decision_id="dec_001",
    rating=5,  # 1-5 scale
    comment="Great call!"
)
```

## API Reference

### DecisionTracker

```python
# Record decision
tracker.record_decision(decision)

# Update outcome
tracker.record_outcome(decision_id, spin_result, outcome, profit_loss)

# Add feedback
tracker.add_feedback(decision_id, rating, comment)

# Query decisions
decisions = tracker.get_decision(decision_id)
decisions = tracker.get_decisions_by_session(session_id)
decisions = tracker.get_decisions_by_target("34")
decisions = tracker.get_decisions_by_source("manual")

# Get statistics
stats = tracker.get_decision_stats()
```

### LearningEngine

```python
# Analyze what works
patterns = learning_engine.analyze_decision_patterns()

# Your betting style
style = learning_engine.identify_player_style()

# All learned patterns
learned = learning_engine.learn_winning_patterns()

# Complete profile
profile = learning_engine.get_player_profile()

# Predict decision quality
prediction = learning_engine.predict_decision_quality(decision)

# Compare manual vs AI
comparison = learning_engine.compare_decision_quality(manual, ai)

# Get tips
tips = learning_engine.get_decision_improvement_tips()
```

### AdaptiveRecommender

```python
# Personalized recommendations
recs = adaptive_recommender.get_personalized_recommendations(recent_spins)

# Your best bets based on history
best = adaptive_recommender.get_learned_best_bets()

# Bets to avoid
avoid = adaptive_recommender.get_decisions_to_avoid()

# Should you follow a recommendation?
decision = adaptive_recommender.should_accept_recommendation(recommendation)

# Betting style tips
tips = adaptive_recommender.get_betting_style_recommendations()

# Complete suggestion for next spin
suggestion = adaptive_recommender.generate_next_spin_suggestion(recent_spins)

# Adaptive confidence
conf = adaptive_recommender.get_adaptive_confidence(recommendation)
```

## Usage Examples

### Example 1: Track a Session

```python
session_id = "session_20260521_001"
for spin_number, (winning_number, bets_placed) in enumerate(spins, 1):
    for bet in bets_placed:
        # Record the decision
        decision = Decision(
            decision_id=f"{session_id}_{spin_number}_{bet['target']}",
            session_id=session_id,
            spin_number=spin_number,
            bet_target=bet['target'],
            bet_type=bet['type'],
            bet_amount=bet['amount'],
            decision_context=bet.get('context', {}),
            source=bet.get('source', 'manual'),
            decision_time=datetime.now(),
            spin_result=None,
            outcome="pending",
            profit_loss=None
        )
        decision_tracker.record_decision(decision)
    
    # After spin result
    for bet in bets_placed:
        decision_id = f"{session_id}_{spin_number}_{bet['target']}"
        outcome = "win" if winning_number in bet['numbers'] else "loss"
        profit = bet['amount'] if outcome == "win" else -bet['amount']
        
        decision_tracker.record_outcome(decision_id, winning_number, outcome, profit)
```

### Example 2: Get Next Spin Suggestion

```python
# Get a complete recommendation for the next spin
suggestion = adaptive_recommender.generate_next_spin_suggestion(recent_spins)

print(f"Suggested Bet: {suggestion['suggested_bet']}")
print(f"Confidence: {suggestion['confidence']:.0%}")
print(f"Reason: {suggestion['reason']}")
print(f"Your History: {suggestion['your_history']}")
print(f"Recommendation Strength: {suggestion['recommendation_strength']}")
```

### Example 3: Evaluate a Recommendation

```python
# Before accepting a recommendation, evaluate it against your history
evaluation = adaptive_recommender.should_accept_recommendation(recommendation)

if evaluation['should_follow']:
    print(f"FOLLOW: {evaluation['reason']}")
    print(f"Adjusted Confidence: {evaluation['confidence']:.0%}")
else:
    print(f"SKIP: You struggle with this bet")
    print(f"Your Win Rate: {evaluation['your_win_rate']:.0%}")
```

### Example 4: Get Player Profile

```python
# Complete analysis of the player
profile = learning_engine.get_player_profile()

print("=== YOUR PLAYER PROFILE ===")
print(f"Total Decisions: {profile['profile_summary']['total_decisions']}")
print(f"Win Rate: {profile['profile_summary']['overall_win_rate']:.0%}")
print(f"Total Profit: ${profile['profile_summary']['total_profit']:.2f}")
print(f"AI Alignment: {profile['profile_summary']['ai_alignment']}")
print(f"Best Bet: {profile['profile_summary']['best_bet_target']}")

print("\nYour Best Bets:")
for target in profile['performance_analysis']['best_targets'][:3]:
    print(f"  • {target['bet_target']}: {target['win_rate']:.0%}")

print("\nStyle Recommendations:")
style_recs = adaptive_recommender.get_betting_style_recommendations()
print(f"  Frequency: {style_recs['betting_frequency']}")
print(f"  Bet Sizing: {style_recs['bet_sizing']}")
print(f"  Risk Level: {style_recs['risk_level']}")
```

## UI Integration Points

### 1. Add Decision Recording to Main Betting Flow

```python
def on_spin(winning_number):
    # Record all bets placed
    for bet in self.current_bets:
        decision = Decision(
            # ... populate fields ...
        )
        self.decision_tracker.record_decision(decision)
    
    # Record outcomes
    for bet in self.current_bets:
        outcome = "win" if winning_number in get_numbers(bet['target']) else "loss"
        self.decision_tracker.record_outcome(
            decision_id=bet['decision_id'],
            spin_result=winning_number,
            outcome=outcome,
            profit_loss=calculate_profit(bet, outcome)
        )
```

### 2. Show Personalized Recommendations

```python
def update_recommendations():
    recs = self.adaptive_recommender.get_personalized_recommendations(self.recent_spins)
    
    for i, rec in enumerate(recs[:3]):
        print(f"Bet {i+1}: {rec['target']}")
        print(f"  Confidence: {rec['confidence']:.0%}")
        if rec.get('personalized'):
            print(f"  ⭐ PERSONALIZED - You're good with this!")
        if rec.get('your_historical_win_rate'):
            print(f"  Your History: {rec['your_historical_win_rate']:.0%}")
```

### 3. Display Player Profile

```python
def show_player_profile():
    profile = self.learning_engine.get_player_profile()
    
    # Dashboard with profile info
    dashboard = create_dashboard(
        stats=profile['decision_statistics'],
        style=profile['player_style'],
        patterns=profile['learned_patterns'],
        summary=profile['profile_summary']
    )
    return dashboard
```

### 4. Show Improvement Tips

```python
def show_tips():
    tips = self.learning_engine.get_decision_improvement_tips()
    style_tips = self.adaptive_recommender.get_betting_style_recommendations()
    
    all_tips = [
        *tips,
        f"Betting Frequency: {style_tips['betting_frequency']}",
        f"Bet Sizing: {style_tips['bet_sizing']}",
        f"Risk Level: {style_tips['risk_level']}"
    ]
    
    return all_tips
```

## Learning Algorithm Details

### 1. Decision Context Features

Each decision extracts:
- Bet target and type
- Decision source (manual/AI)
- Confidence level
- Reason for bet
- Amount tier (micro/small/medium/large)
- Time of day

### 2. Pattern Matching

Patterns are identified by:
- Context hash (unique combination of features)
- Win/loss count at that context
- Average profit at that context
- Confidence score based on data volume

### 3. Adaptive Confidence

Recommendations are boosted/reduced based on:
- Player's historical win rate with that bet
- Number of times player has made that bet
- Deviation from 50% baseline

### 4. Style Detection

Player style determined by:
- Win rate with manual vs AI decisions
- Preferred bet types and targets
- Betting frequency and sizing
- Alignment with AI recommendations

### 5. Improvement Suggestions

Tips generated from:
- Best performing bets
- Worst performing bets
- AI alignment analysis
- Bet sizing optimization
- Risk level recommendation

## Performance Considerations

1. **Database Indices**: Add for faster queries
   ```python
   # Create indices for common queries
   CREATE INDEX idx_decision_target ON decisions(bet_target);
   CREATE INDEX idx_decision_source ON decisions(source);
   ```

2. **Caching**: Cache player profile to avoid recalculation
   ```python
   self.cached_profile = None
   self.profile_cache_time = 0
   
   def get_profile(self):
       if time.time() - self.profile_cache_time > 300:  # 5 min cache
           self.cached_profile = learning_engine.get_player_profile()
           self.profile_cache_time = time.time()
       return self.cached_profile
   ```

3. **Batch Operations**: Save multiple decisions efficiently

## Machine Learning Potential

Future enhancements:
- Cluster similar decisions automatically
- Predict outcomes using classification ML
- Optimize bet sizing with reinforcement learning
- Time-series analysis for session patterns
- Multi-armed bandit for exploration/exploitation

## Next Steps

1. ✅ Integrate with main.py
2. ⏭️ Test with real session data
3. 📊 Add visualization of player profile
4. 📈 Generate detailed player reports
5. 🤖 Implement ML predictions
