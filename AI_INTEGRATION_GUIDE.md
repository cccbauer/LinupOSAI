# LinupOSAI - AI Module Integration Guide

## Architecture Overview

The AI system for Linup consists of four modular components:

### 1. **ai_sessions.py** - Session Repository
Manages complete session storage and retrieval. Persists all betting activity to SQLite database.

**Key Classes:**
- `Session` - Dataclass representing a complete betting session
- `Spin` - Individual spin record with bets
- `Bet` - Individual bet information
- `SessionRepository` - Main database interface

### 2. **ai_patterns.py** - Pattern Detection
Detects various patterns in roulette sequences including number frequencies, group clustering, neighbor patterns, and sequences.

**Key Classes:**
- `PatternDetector` - Analyzes spin results for patterns

**Detection Types:**
- Number frequency patterns (hot/cold numbers)
- Group clustering (when certain groups hit more frequently)
- Wheel neighbor clustering
- Repeating sequences
- Color patterns (red/black trends)
- Odd/even patterns
- Dozen patterns (1-12, 13-24, 25-36)

### 3. **ai_analysis.py** - Pattern Analysis
Aggregates patterns across multiple sessions and identifies dominant trends.

**Key Classes:**
- `PatternAnalyzer` - Statistical analysis of detected patterns

**Analysis Features:**
- Most prevalent patterns across all sessions
- Session performance insights (ROI, profit, etc.)
- Hottest and coldest numbers
- Best performing groups
- Pattern correlations (which patterns appear together)
- Comprehensive reporting

### 4. **ai_recommendations.py** - Betting Recommendations
Generates intelligent betting suggestions based on detected patterns and historical data.

**Key Classes:**
- `RecommendationEngine` - Generates betting recommendations

**Recommendation Types:**
- Hot number bets
- Hot group bets
- Neighbor clustering bets
- Repeating sequence predictions
- Color trend bets
- Optimal bet combinations
- Progression adjustments
- Session forecasts

## Integration Example

### Basic Setup

```python
from ai_sessions import SessionRepository, Session, Spin, Bet
from ai_patterns import PatternDetector
from ai_analysis import PatternAnalyzer
from ai_recommendations import RecommendationEngine
from datetime import datetime

# Initialize repository
repo = SessionRepository("linup_sessions.db")

# Get group definitions from main.py
# (Import GRUPOS_MAESTROS and ROJOS from main.py)
GRUPOS_MAESTROS = { ... }  # From main.py
ROJOS = { ... }  # From main.py
WHEEL_NEIGHBORS = { ... }  # From main.py

# Initialize AI components
detector = PatternDetector(GRUPOS_MAESTROS, WHEEL_NEIGHBORS)
analyzer = PatternAnalyzer(repo)
recommender = RecommendationEngine(detector, analyzer, GRUPOS_MAESTROS)
```

### Saving a Session

```python
# Create spins and bets
bets = [
    Bet(bet_id='34', amount=10, type='group', result='win'),
    Bet(bet_id='R', amount=5, type='group', result='loss'),
]

spin = Spin(
    spin_number=1,
    result=14,  # Winning number
    bets=bets,
    timestamp=datetime.now()
)

# Create and save session
session = Session(
    session_id="session_20240521_001",
    created_at=datetime.now(),
    spins=[spin],
    starting_capital=100.0,
    ending_capital=105.0,
    notes="Test session",
    groups_used=['34', 'R', 'B'],
    progression_mode='fibonacci'
)

repo.save_session(session)

# Detect patterns in this session
patterns = detector.analyze_all_patterns(
    [spin.result for spin in session.spins],
    ROJOS
)

# Save detected patterns
for pattern_type, pattern_data in patterns['patterns'].items():
    if isinstance(pattern_data, list):
        for p in pattern_data:
            repo.save_detected_pattern(
                session.session_id,
                pattern_type,
                p,
                p.get('confidence', 0.5)
            )
    else:
        repo.save_detected_pattern(
            session.session_id,
            pattern_type,
            pattern_data,
            0.5
        )
```

### Getting Betting Recommendations

```python
# Get recent spins (from current session or loaded sessions)
recent_spins = [14, 7, 23, 1, 36, 18, 5, 21, 0, 12]

# Generate recommendations
recommendations = recommender.generate_spin_recommendations(recent_spins)

for rec in recommendations:
    print(f"Bet: {rec['target']} (Type: {rec['type']})")
    print(f"  Confidence: {rec['confidence']:.0%}")
    print(f"  Reason: {rec['reason']}")
    print(f"  Bet Type: {rec['bet_type']}")
    print()

# Get optimal combination
optimal = recommender.get_optimal_bet_combination(recommendations)
print(f"Recommended bets: {len(optimal['recommended_bets'])}")
for bet in optimal['recommended_bets']:
    print(f"  - {bet['target']}: {bet['reason']}")
```

### Analyzing Patterns

```python
# Get most prevalent patterns
prevalent = analyzer.get_most_prevalent_patterns(limit=10)

print("Most Prevalent Patterns:")
for pattern in prevalent:
    print(f"  {pattern['pattern_type']}: {pattern['occurrences']} times")
    print(f"    Confidence: {pattern['average_confidence']:.0%}")

# Get session performance
performance = analyzer.get_session_performance_insights()

print(f"Total Sessions: {performance['total_sessions']}")
print(f"Average ROI: {performance['average_roi']:.1%}")
print(f"Total Profit: ${performance['total_profit']:.2f}")
print(f"Winning Sessions: {performance['winning_sessions']}")

# Get hot and cold numbers
hottest = analyzer.get_hottest_numbers(window_sessions=10)
coldest = analyzer.get_coldest_numbers(window_sessions=10)

print(f"\nHottest numbers:")
for num, hits, freq in hottest[:5]:
    print(f"  {num}: {freq:.1%} ({hits} hits)")

print(f"\nColdest numbers:")
for num, hits, freq in coldest[:5]:
    print(f"  {num}: {freq:.1%} ({hits} hits)")
```

### Generating Comprehensive Report

```python
# Generate full analysis report
report = analyzer.generate_comprehensive_report()

print("=== LINUP AI ANALYSIS REPORT ===")
print(f"Generated: {report['generated_at']}")
print(f"\nSession Statistics:")
print(f"  Total Sessions: {report['database_stats']['total_sessions']}")
print(f"  Total Spins: {report['database_stats']['total_spins']}")
print(f"  Total Patterns Detected: {report['database_stats']['total_patterns_detected']}")

print(f"\nPerformance:")
print(f"  Average ROI: {report['performance']['average_roi']:.1%}")
print(f"  Best ROI: {report['performance']['best_roi']:.1%}")
print(f"  Worst ROI: {report['performance']['worst_roi']:.1%}")

print(f"\nTop Patterns:")
for pattern in report['prevalent_patterns'][:5]:
    print(f"  {pattern['pattern_type']}: {pattern['occurrences']} occurrences")

print(f"\nTop Groups:")
for group in report['best_groups'][:3]:
    print(f"  {group['group']}: {group['win_rate']:.0%} win rate")
```

## Integration Points with main.py

### 1. Session Initialization
At the start of a new session, create a SessionRepository instance:

```python
# In main.py initialization
self.session_repo = SessionRepository()
self.pattern_detector = PatternDetector(GRUPOS_MAESTROS, WHEEL_NEIGHBORS)
self.analyzer = PatternAnalyzer(self.session_repo)
self.recommender = RecommendationEngine(self.pattern_detector, self.analyzer, GRUPOS_MAESTROS)
self.current_spins = []
```

### 2. After Each Spin
Record the spin result and analyze:

```python
# After a spin result is known
self.current_spins.append(winning_number)

# Generate recommendations for next spin (if enough history)
if len(self.current_spins) >= 5:
    recommendations = self.recommender.generate_spin_recommendations(self.current_spins)
    # Display recommendations in UI
```

### 3. Session Completion
Save complete session to repository:

```python
# At end of session
from datetime import datetime

session = Session(
    session_id=f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    created_at=datetime.now(),
    spins=self.session_spins,  # List of Spin objects
    starting_capital=starting_balance,
    ending_capital=current_balance,
    notes=session_notes,
    groups_used=list(self.active_groups),
    progression_mode=self.progression_type
)

self.session_repo.save_session(session)

# Detect and save patterns from this session
patterns = self.pattern_detector.analyze_all_patterns(self.current_spins, ROJOS)
for pattern_type, pattern_data in patterns['patterns'].items():
    # Save patterns to database
```

### 4. UI Displays
Show AI insights in the Flet UI:

#### Pattern Analysis View
```python
def show_pattern_analysis(self):
    report = self.analyzer.generate_comprehensive_report()
    
    # Display in a ScrollView or Column
    patterns_text = f"""
    Prevalent Patterns:
    {json.dumps(report['prevalent_patterns'][:5], indent=2)}
    """
    
    # Add to UI
    return ft.Text(patterns_text)
```

#### Recommendations View
```python
def show_recommendations(self):
    recs = self.recommender.generate_spin_recommendations(self.current_spins)
    
    recommendation_items = []
    for rec in recs[:5]:
        recommendation_items.append(
            ft.Container(
                content=ft.Column([
                    ft.Text(f"Bet: {rec['target']}", weight="bold"),
                    ft.Text(f"Confidence: {rec['confidence']:.0%}"),
                    ft.Text(f"Reason: {rec['reason']}", italic=True),
                ]),
                border=ft.border.all(1)
            )
        )
    
    return ft.Column(recommendation_items)
```

#### Dashboard View
```python
def show_dashboard(self):
    stats = self.analyzer.get_session_performance_insights()
    hottest = self.analyzer.get_hottest_numbers()
    best_groups = self.analyzer.get_best_performing_groups()
    
    dashboard = ft.Column([
        ft.Text("AI Dashboard", size=20, weight="bold"),
        ft.Divider(),
        
        # Statistics
        ft.Row([
            ft.Text(f"Sessions: {stats['total_sessions']}"),
            ft.Text(f"Avg ROI: {stats['average_roi']:.1%}"),
            ft.Text(f"Total Profit: ${stats['total_profit']:.2f}"),
        ]),
        
        # Hot Numbers
        ft.Text("Hot Numbers:", weight="bold"),
        ft.Row([ft.Text(str(h[0])) for h in hottest[:10]]),
        
        # Best Groups
        ft.Text("Best Groups:", weight="bold"),
        ft.Column([
            ft.Text(f"{g['group']}: {g['win_rate']:.0%}")
            for g in best_groups[:5]
        ])
    ])
    
    return dashboard
```

## Database Schema

The SQLite database includes these tables:

```sql
-- Session metadata
sessions (session_id, created_at, starting_capital, ending_capital, 
          total_spins, win_count, loss_count, roi, notes, groups_used, 
          progression_mode)

-- Individual spins
spins (spin_id, session_id, spin_number, result_number, timestamp)

-- Individual bets
bets (bet_id, spin_id, bet_name, amount, bet_type, bet_result)

-- Detected patterns
detected_patterns (pattern_id, session_id, pattern_type, pattern_data, 
                  confidence, detected_at)
```

## Configuration and Tuning

### Pattern Detection Thresholds
Adjust confidence thresholds in pattern detection methods:

```python
# In detect_number_frequency_patterns()
hot_threshold = expected_frequency * 1.5  # Increase for stricter detection
cold_threshold = expected_frequency * 0.5

# In detect_group_clustering()
deviation_threshold = expected_rate * 0.3  # 30% deviation threshold
```

### Recommendation Filtering
Adjust recommendation confidence threshold:

```python
recommendations = recommender.generate_spin_recommendations(
    recent_spins, 
    confidence_threshold=0.45  # Lower = more recommendations (but less reliable)
)
```

### Analysis Window Sizes
Customize how many recent sessions/spins to analyze:

```python
analyzer.get_hottest_numbers(window_sessions=15)  # Analyze last 15 sessions
detector.detect_group_clustering(spin_results, window_size=30)  # Analyze last 30 spins
```

## Performance Considerations

1. **Database Indexing**: Add indices for faster queries:
   ```python
   # After first run, manually add indices:
   # CREATE INDEX idx_session_date ON sessions(created_at);
   # CREATE INDEX idx_spin_result ON spins(result_number);
   ```

2. **Pattern Analysis Cache**: Cache comprehensive reports to avoid recalculation:
   ```python
   self.cached_report = None
   self.cache_timestamp = 0
   
   def get_report(self):
       if time.time() - self.cache_timestamp > 300:  # 5 minute cache
           self.cached_report = self.analyzer.generate_comprehensive_report()
           self.cache_timestamp = time.time()
       return self.cached_report
   ```

3. **Batch Processing**: Save multiple patterns in batch:
   ```python
   for pattern in patterns_list:
       repo.save_detected_pattern(...)
   ```

## Next Steps

1. **Integrate with main.py** - Add UI views for AI features
2. **Add Visualization** - Create charts for pattern trends
3. **Export Reports** - Generate CSV/PDF analysis reports
4. **Mobile Sync** - Sync sessions across devices
5. **Advanced ML** - Implement ML models for improved predictions
