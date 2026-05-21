# LinupOSAI - AI Features Quick Reference

## 🎯 What's New

LinupOSAI now includes a complete AI analysis system that:

- ✅ **Stores ALL sessions** in a persistent repository
- ✅ **Detects patterns** automatically from your betting sequences
- ✅ **Analyzes predominant patterns** to find what works best for you
- ✅ **Generates betting recommendations** based on historical patterns
- ✅ **Provides insights** about your performance and trends

---

## 📁 New Files Created

### Core AI Modules
1. **ai_sessions.py** - Session storage and retrieval
2. **ai_patterns.py** - Pattern detection algorithms
3. **ai_analysis.py** - Cross-session pattern analysis
4. **ai_recommendations.py** - Betting recommendations engine

### Documentation & Examples
5. **AI_INTEGRATION_GUIDE.md** - Complete integration guide
6. **ai_demo.py** - Working examples of all features

---

## 🔍 Pattern Types Detected

The AI automatically detects 7 different pattern types:

1. **Number Frequency** - Which numbers are "hot" or "cold"
2. **Group Clustering** - Which betting groups are performing well
3. **Neighbor Clustering** - Patterns based on wheel position neighbors
4. **Repeating Sequences** - Recurring number sequences
5. **Color Patterns** - Red/Black trends and runs
6. **Odd/Even Patterns** - Distribution patterns
7. **Dozen Patterns** - Performance by dozens (1-12, 13-24, 25-36)

---

## 💡 Key Features

### 1. Session Repository
```python
repo = SessionRepository("linup_sessions.db")
repo.save_session(session)
repo.get_all_sessions()
repo.get_database_stats()
```

### 2. Pattern Detection
```python
detector = PatternDetector(GRUPOS_MAESTROS, WHEEL_NEIGHBORS)
patterns = detector.analyze_all_patterns(spin_results, ROJOS)
```

### 3. Pattern Analysis
```python
analyzer = PatternAnalyzer(repo)
prevalent = analyzer.get_most_prevalent_patterns()
hottest = analyzer.get_hottest_numbers()
performance = analyzer.get_session_performance_insights()
```

### 4. Recommendations
```python
recommender = RecommendationEngine(detector, analyzer, GRUPOS_MAESTROS)
recommendations = recommender.generate_spin_recommendations(recent_spins)
optimal = recommender.get_optimal_bet_combination(recommendations)
```

---

## 📊 Analysis Capabilities

### Performance Metrics
- Total sessions and spins tracked
- ROI (Return on Investment) analysis
- Win/loss/breakeven session counts
- Profit/loss calculations

### Pattern Insights
- Most frequently occurring patterns
- Pattern confidence scores
- Pattern correlations (which patterns appear together)
- Pattern trends over time

### Number Analysis
- Hot numbers (appearing more frequently than expected)
- Cold numbers (appearing less frequently than expected)
- Frequency percentages and occurrence counts

### Group Analysis
- Best performing betting groups
- Win rates by group
- Group clustering trends

---

## 🚀 Quick Start

### 1. Run the Demo
```bash
python ai_demo.py
```

This will:
- Create a sample session
- Detect patterns
- Analyze performance
- Generate recommendations
- Store everything in the database

### 2. Integrate with main.py
See `AI_INTEGRATION_GUIDE.md` for integration points and code examples.

### 3. Access the Data
```python
# Get all sessions
sessions = repo.get_all_sessions()

# Get comprehensive report
report = analyzer.generate_comprehensive_report()

# Get next spin recommendations
recs = recommender.generate_spin_recommendations(recent_spins)
```

---

## 📈 Database Structure

The system uses SQLite with 4 main tables:

1. **sessions** - Session metadata (capital, ROI, groups used, etc.)
2. **spins** - Individual spin records (number results, timestamps)
3. **bets** - Individual bets placed (amount, result, type)
4. **detected_patterns** - Stored patterns with confidence scores

All data is automatically indexed for fast queries.

---

## 🎮 Integration Points with main.py

### Add to your session initialization:
```python
from ai_sessions import SessionRepository
from ai_patterns import PatternDetector
from ai_analysis import PatternAnalyzer
from ai_recommendations import RecommendationEngine

self.session_repo = SessionRepository()
self.detector = PatternDetector(GRUPOS_MAESTROS, WHEEL_NEIGHBORS)
self.analyzer = PatternAnalyzer(self.session_repo)
self.recommender = RecommendationEngine(self.detector, self.analyzer, GRUPOS_MAESTROS)
```

### After each spin:
```python
self.current_spins.append(winning_number)

# Get recommendations for next spin
if len(self.current_spins) >= 5:
    recommendations = self.recommender.generate_spin_recommendations(self.current_spins)
    # Display recommendations in UI
```

### At session end:
```python
session = Session(
    session_id=session_id,
    created_at=datetime.now(),
    spins=self.session_spins,
    starting_capital=starting,
    ending_capital=ending,
    notes=notes,
    groups_used=list(self.active_groups),
    progression_mode=self.progression_type
)
self.session_repo.save_session(session)
```

---

## 📊 UI Views You Can Add

### 1. Pattern Analysis Dashboard
```
╔═══════════════════════════════════╗
║  PATTERN ANALYSIS                 ║
║─────────────────────────────────  ║
║  Prevalent Patterns:              ║
║  • Group Clustering (45x)         ║
║  • Number Frequency (38x)         ║
║  • Color Patterns (32x)           ║
║                                   ║
║  Hot Numbers: 14, 7, 23, 18      ║
║  Cold Numbers: 0, 2, 4, 6        ║
╚═══════════════════════════════════╝
```

### 2. AI Recommendations Panel
```
╔═══════════════════════════════════╗
║  NEXT SPIN RECOMMENDATIONS        ║
║─────────────────────────────────  ║
║  1. Bet: 34 (68% confidence)     ║
║     Reason: Group clustering     ║
║                                   ║
║  2. Bet: R (52% confidence)      ║
║     Reason: Red color trend      ║
║                                   ║
║  3. Bet: 14 (46% confidence)     ║
║     Reason: Hot number           ║
╚═══════════════════════════════════╝
```

### 3. Performance Report
```
╔═══════════════════════════════════╗
║  PERFORMANCE REPORT               ║
║─────────────────────────────────  ║
║  Total Sessions: 42               ║
║  Average ROI: +8.3%               ║
║  Total Profit: $347.50            ║
║  Winning Sessions: 28             ║
║  Winning Groups: 34, 35, Z0       ║
╚═══════════════════════════════════╝
```

---

## 🔧 Configuration

### Adjust Pattern Detection Sensitivity
```python
# In ai_patterns.py
hot_threshold = expected_frequency * 2  # More strict
cold_threshold = expected_frequency * 0.25  # Less strict
```

### Change Recommendation Confidence Threshold
```python
recs = recommender.generate_spin_recommendations(
    recent_spins, 
    confidence_threshold=0.50  # Higher = fewer, more confident recommendations
)
```

### Customize Analysis Window
```python
analyzer.get_hottest_numbers(window_sessions=20)  # Last 20 sessions
detector.detect_group_clustering(spins, window_size=40)  # Last 40 spins
```

---

## 📚 Next Steps

1. **✅ Run ai_demo.py** to test all features
2. **⏭️ Integrate with main.py** - Add AI modules to your Flet app
3. **🎨 Add UI Views** - Create dashboard, recommendations panel, insights viewer
4. **📊 Generate Reports** - Export analysis as CSV/PDF
5. **🤖 Advanced ML** - Add machine learning models for improved predictions

---

## 📞 Support

For detailed integration help, see `AI_INTEGRATION_GUIDE.md`

For working examples, check `ai_demo.py`

For API reference, see docstrings in each module:
- `ai_sessions.py` - Session storage
- `ai_patterns.py` - Pattern detection
- `ai_analysis.py` - Analysis
- `ai_recommendations.py` - Recommendations

---

## 🎯 Key Metrics You'll Now Track

- **Spin History**: Every spin result is stored
- **Pattern Frequency**: How often each pattern appears
- **Pattern Confidence**: How reliable each pattern is
- **Group Performance**: Win rate by betting group
- **Number Distribution**: Hot/cold number analysis
- **Session ROI**: Return on investment per session
- **Trend Analysis**: Performance trends over time
- **Correlation Analysis**: Which patterns appear together

---

## 💾 Database Location

Default: `linup_sessions.db` in project root

Contains your complete session history with all patterns and analysis data.

**Never delete this file!** It's your complete betting history and pattern database.

---

**Ready to enhance your Linup with AI? Run `python ai_demo.py` to get started!** 🚀
