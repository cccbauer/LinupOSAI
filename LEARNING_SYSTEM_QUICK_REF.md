# LinupOSAI Learning System - Quick Reference

## 🧠 What's New

The **Learning System** enables Linup to learn YOUR unique betting style and adapt recommendations accordingly. It:

✅ **Records every decision** - What you bet, when, why, and what happened
✅ **Learns from outcomes** - Identifies which of your decisions are profitable
✅ **Builds your profile** - Understands your betting style and preferences
✅ **Adapts recommendations** - Gives suggestions based on YOUR history, not just general patterns
✅ **Provides tips** - Tells you what you're good at and what to avoid

## 📁 New Files

1. **ai_decision_tracker.py** (420 lines) - Records decisions and outcomes
2. **ai_learning_engine.py** (480 lines) - Learns from your decisions
3. **ai_adaptive_recommender.py** (350 lines) - Personalized suggestions
4. **ai_learning_demo.py** (370 lines) - Working examples
5. **LEARNING_SYSTEM_GUIDE.md** - Complete integration guide

## 🎯 Core Concepts

### Decision
A single bet you made with context:
```python
Decision(
    decision_id="dec_001",
    bet_target="34",           # What you bet
    bet_type="group",          # group or number
    source="manual",           # Who suggested it
    decision_time=datetime.now(),
    outcome="win",             # Result
    profit_loss=10,            # P&L
    player_satisfaction=5      # Your feedback
)
```

### Pattern
A recurring successful decision type:
- "When I bet on group '34', I win 85% of the time"
- "My manual decisions perform better than AI suggestions"
- "I do well with small bets, struggle with large bets"

### Profile
Your complete betting personality:
- Win rates by bet type
- Preferred betting targets
- AI alignment (do you trust AI or your intuition?)
- Best bet size and frequency
- Risk tolerance level

## 🔧 Quick API

### Recording a Decision

```python
from ai_decision_tracker import DecisionTracker, Decision

tracker = DecisionTracker()

# When player makes a bet
decision = Decision(
    decision_id="unique_id",
    session_id="session_001",
    spin_number=5,
    bet_target="34",
    bet_type="group",
    bet_amount=10,
    decision_context={'confidence': 0.7, 'reason': 'Hot group'},
    source="manual",  # or "ai_recommendation"
    decision_time=datetime.now(),
    spin_result=None,  # Filled after spin
    outcome="pending",
    profit_loss=None
)

tracker.record_decision(decision)

# After spin result is known
tracker.record_outcome(
    decision_id="unique_id",
    spin_result=14,
    outcome="win",  # or "loss"
    profit_loss=10
)

# Optional: Get feedback from player
tracker.add_feedback(decision_id="unique_id", rating=5, comment="Great!")
```

### Learning from Decisions

```python
from ai_learning_engine import LearningEngine

learner = LearningEngine(tracker)

# Analyze what works
patterns = learner.analyze_decision_patterns()
# Returns: {best_targets, worst_targets, win_rates}

# Your betting style
style = learner.identify_player_style()
# Returns: {ai_alignment, preferred_bet_types, win_rate}

# Get tips for improvement
tips = learner.get_decision_improvement_tips()
# Returns: ["Your best bets are...", "Avoid betting...", ...]

# Complete profile
profile = learner.get_player_profile()
# Returns: {statistics, style, patterns, analysis}
```

### Personalized Recommendations

```python
from ai_adaptive_recommender import AdaptiveRecommender

adapter = AdaptiveRecommender(base_recommender, learner, tracker)

# Personalized recommendations (boosted for YOUR best bets)
recs = adapter.get_personalized_recommendations(recent_spins)
# Each recommendation now includes:
# - your_historical_win_rate
# - personalized: True if boosted based on your profile

# Your best bets (learned from history)
best = adapter.get_learned_best_bets()
# Returns: [{target, win_rate, avg_profit, total_profit, ...}]

# Should you follow a recommendation?
eval = adapter.should_accept_recommendation(recommendation)
# Returns: {should_follow, your_win_rate, recommendation_strength}

# Complete suggestion for next spin
suggestion = adapter.generate_next_spin_suggestion(recent_spins)
# Returns: {suggested_bet, confidence, reason, your_history, alternatives}
```

## 📊 Learning Features

### 1. Decision Tracking
- Records: bet, source, context, outcome, profit/loss
- Tracks: manual vs AI recommendations
- Feedback: optional player satisfaction rating

### 2. Pattern Learning
- Identifies: recurring successful decision patterns
- Calculates: win rates, profit averages, confidence
- Learns: your personal "golden rules"

### 3. Player Profiling
- Analyzes: your betting style and preferences
- Detects: which bets work best for YOU
- Tracks: AI alignment (trust AI or intuition?)

### 4. Recommendation Adaptation
- Boosts: recommendations for your best bets
- Warns: against bets you struggle with
- Personalizes: suggestions based on YOUR history

### 5. Improvement Tips
- Identifies: your best performing bets
- Recommends: optimal bet sizing
- Suggests: frequency and risk level adjustments

## 📈 Example Output

### Decision Stats
```
Total Decisions: 127
Win Rate: 58%
Total Profit: $234.50
Sources: {manual: 89, ai_recommendation: 38}
```

### Your Best Bets
```
1. Group '34': 68% win rate ($12.50 avg profit)
2. Color 'R': 62% win rate ($8.30 avg profit)
3. Group '35': 55% win rate ($5.20 avg profit)
```

### Your Style
```
AI Alignment: TRUSTS_INTUITION
Best Bet Size: Medium ($15-30)
Betting Frequency: Moderate (2-3 per spin)
Risk Level: BALANCED
```

### Recommendations with Your History
```
Recommendation 1: Bet '34'
  AI Confidence: 70%
  Your Win Rate: 68% (from 25 bets)
  Recommendation Strength: FOLLOW (95% confidence)

Recommendation 2: Bet 'R'
  AI Confidence: 60%
  Your Win Rate: 62% (from 18 bets)
  Recommendation Strength: FOLLOW (88% confidence)

Recommendation 3: Bet '12'
  AI Confidence: 55%
  Your Win Rate: 35% (from 8 bets)
  Recommendation Strength: SKIP (25% confidence)
```

## 🎓 How the Learning Works

### Phase 1: Recording
Every decision is recorded with:
- What you bet
- Why you bet it (context)
- Who suggested it (you or AI)
- Whether it won or lost
- How much you won/lost

### Phase 2: Analysis
System finds patterns:
- Which bets work best for YOU
- Which bets don't work
- When you're most successful
- If AI or your intuition works better

### Phase 3: Adaptation
Recommendations adjust to:
- Boost your best bets
- Warn about your weak spots
- Match your risk tolerance
- Fit your preferred style

### Phase 4: Learning
Continuous improvement:
- More decisions = more accurate learning
- Feedback improves personalization
- Patterns become more reliable
- Recommendations get better over time

## 🚀 Integration Checklist

- [ ] Initialize DecisionTracker
- [ ] Initialize LearningEngine
- [ ] Initialize AdaptiveRecommender
- [ ] Record decision when player places bet
- [ ] Record outcome when spin completes
- [ ] Collect player feedback (optional)
- [ ] Show personalized recommendations instead of base recommendations
- [ ] Display player profile in dashboard
- [ ] Show improvement tips
- [ ] Display "Your Best Bets" and "Bets to Avoid"

## 💡 Real-World Example

### Session Flow

```
1. Player starts betting
   → Record each decision

2. Player bets on '34'
   → Decision recorded with: confidence 0.75, source="manual"

3. Spin result: 14 (loses)
   → Record outcome: loss, profit_loss=-10

4. System analyzes
   → Learns: Player has lost betting on '34' recently

5. Next spin, system recommends '35'
   → Includes: "34 recommendation would be 60% confidence"
   → But reduced to 40% because you recently lost on '34'

6. Player eventually bets many times on '34'
   → System notices: 70% win rate when you bet on '34'
   → Boosts confidence: "You're very good with '34'!"
   → Personalizes: Always recommends '34' when pattern fits

7. Player provides feedback rating 5/5 on winning bets
   → System learns: These patterns are really working for you
   → Increases confidence in similar recommendations
```

## 📊 Database Structure

```sql
decisions                -- Every decision (127 rows per active player)
├─ decision_id
├─ bet_target ('34', 'R', '14', etc)
├─ source ('manual' or 'ai_recommendation')
├─ outcome ('win', 'loss', 'pending')
├─ profit_loss (+10, -5, etc)
└─ player_satisfaction (1-5 rating)

decision_feedback        -- Optional feedback from player
├─ decision_id
├─ rating (1-5)
└─ comment

learned_patterns         -- Discovered patterns
├─ pattern_key ('34_manual', 'R_ai', etc)
├─ win_count (68 wins)
├─ loss_count (32 losses)
├─ confidence (0-100%)
└─ average_profit ($12.50)
```

## 🎯 Key Metrics Tracked

- **Decision Count**: Total decisions made
- **Win Rate**: % of winning decisions
- **Total Profit**: Overall P&L
- **Best Bets**: Highest win rate targets
- **Worst Bets**: Lowest win rate targets
- **Avg Profit per Decision**: P&L per bet
- **AI Alignment**: How well you follow AI
- **Decision Sources**: Manual vs AI ratio

## 🔄 Feedback Loop

```
Decision Made
    ↓
Outcome Recorded
    ↓
Pattern Detected (after 3+ similar decisions)
    ↓
Player Feedback (optional rating)
    ↓
Profile Updated
    ↓
Next Recommendation Improved
    ↓
Repeat...
```

## ⚡ Key Insight

The learning system doesn't try to predict roulette. Instead, it learns **YOUR** patterns:
- What YOU consistently win on
- What YOU consistently lose on
- When YOU make your best decisions
- When YOU should trust AI vs your intuition

This is far more valuable than general patterns!

## 🎮 UI Suggestions

### Display in Main UI
```
Next Spin Recommendation: Bet '34'
├─ AI Confidence: 70%
├─ YOUR Win Rate: 68% (25 bets)
└─ Adjusted Confidence: 95% ⭐

Your Best Bets This Session:
├─ '34': 8/10 wins
├─ 'R': 6/8 wins
└─ '35': 5/9 wins

Bets to Avoid:
└─ '12': Only 2/8 wins (25%)
```

### Dashboard View
```
Player Profile
├─ Total Decisions: 127
├─ Overall Win Rate: 58%
├─ Best Bet: Group '34' (68% win rate)
├─ AI Alignment: Trusts Intuition
└─ Recommendation: Stay focused on '34' and 'R'
```

## 📞 Support

See `LEARNING_SYSTEM_GUIDE.md` for detailed integration and API docs.

See `ai_learning_demo.py` for working code examples.

---

**Ready to teach Linup how to adapt to YOUR style?** The learning system is ready to go! 🧠🚀
