"""
AI Demo Script - Example usage of LinupOSAI AI modules
Demonstrates how to use all AI components together
"""

from ai_sessions import SessionRepository, Session, Spin, Bet
from ai_patterns import PatternDetector
from ai_analysis import PatternAnalyzer
from ai_recommendations import RecommendationEngine
from datetime import datetime
import json

# ============================================================================
# GROUP DEFINITIONS (from main.py)
# ============================================================================

ROJOS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

GRUPOS_MAESTROS = {
    '34': {1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34},
    '35': {2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35},
    '36': {3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36},
    '1a': set(range(1, 13)),
    '2a': set(range(13, 25)),
    '3a': set(range(25, 37)),
    'R': ROJOS,
    'B': set(range(1, 37)) - ROJOS,
    'Even': {n for n in range(2, 37, 2)},
    'Odd': {n for n in range(1, 37, 2)},
    '1-18': set(range(1, 19)),
    '19-36': set(range(19, 37)),
}

WHEEL_ORDER = [0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26]
WHEEL_NEIGHBORS = {
    n: {WHEEL_ORDER[(i - 1) % 37], WHEEL_ORDER[(i + 1) % 37]}
    for i, n in enumerate(WHEEL_ORDER)
}

# ============================================================================
# DEMO FUNCTIONS
# ============================================================================

def demo_1_session_creation():
    """Demo 1: Create and save a session"""
    print("\n" + "="*70)
    print("DEMO 1: Session Creation and Storage")
    print("="*70)
    
    repo = SessionRepository("demo_sessions.db")
    
    # Create sample spin results
    spin_results = [14, 7, 23, 1, 36, 18, 5, 21, 0, 12, 14, 7, 23, 1, 36]
    
    # Create Spin objects with bets
    spins = []
    for i, num in enumerate(spin_results):
        # Create bets for this spin
        bets = [
            Bet(bet_id='34', amount=10, type='group', result='win' if num in GRUPOS_MAESTROS['34'] else 'loss'),
            Bet(bet_id='R', amount=5, type='group', result='win' if num in ROJOS else 'loss'),
        ]
        
        spin = Spin(
            spin_number=i + 1,
            result=num,
            bets=bets,
            timestamp=datetime.now()
        )
        spins.append(spin)
    
    # Create session
    session = Session(
        session_id="demo_session_001",
        created_at=datetime.now(),
        spins=spins,
        starting_capital=100.0,
        ending_capital=115.0,
        notes="Demo session for AI module testing",
        groups_used=['34', 'R', '1a'],
        progression_mode='fibonacci'
    )
    
    # Save session
    success = repo.save_session(session)
    print(f"✓ Session saved: {success}")
    print(f"  Session ID: {session.session_id}")
    print(f"  Total Spins: {len(spins)}")
    print(f"  Starting Capital: ${session.starting_capital}")
    print(f"  Ending Capital: ${session.ending_capital}")
    print(f"  ROI: {(session.ending_capital - session.starting_capital) / session.starting_capital * 100:.1f}%")
    
    return repo, spin_results


def demo_2_pattern_detection(spin_results):
    """Demo 2: Detect patterns in spins"""
    print("\n" + "="*70)
    print("DEMO 2: Pattern Detection")
    print("="*70)
    
    detector = PatternDetector(GRUPOS_MAESTROS, WHEEL_NEIGHBORS)
    
    # Run comprehensive pattern analysis
    patterns = detector.analyze_all_patterns(spin_results, ROJOS)
    
    print(f"Analysis Date: {patterns['analysis_time']}")
    print(f"Total Spins Analyzed: {patterns['total_spins']}")
    print("\nDetected Patterns:")
    
    # Number frequency
    if 'number_frequency' in patterns['patterns']:
        nf = patterns['patterns']['number_frequency']
        print(f"\n📊 Number Frequency:")
        if nf.get('hot_numbers'):
            print(f"  Hot Numbers: {list(nf['hot_numbers'].keys())}")
            for num, freq in nf['hot_numbers'].items():
                print(f"    - {num}: {freq:.1%}")
    
    # Group clustering
    if 'group_clustering' in patterns['patterns']:
        gc = patterns['patterns']['group_clustering']
        print(f"\n👥 Group Clustering (Top 3):")
        for i, group in enumerate(gc[:3]):
            print(f"  {group['group']}: {group['hit_rate']:.1%} " +
                  f"(deviation: {group['deviation']:+.1%}, confidence: {group['confidence']:.0%})")
    
    # Repeating sequences
    if 'repeating_sequences' in patterns['patterns'] and patterns['patterns']['repeating_sequences']:
        print(f"\n🔄 Repeating Sequences:")
        for seq in patterns['patterns']['repeating_sequences'][:3]:
            print(f"  {seq['sequence']} (appeared {seq['occurrences']} times)")
    
    # Color patterns
    if 'color_patterns' in patterns['patterns']:
        cp = patterns['patterns']['color_patterns']
        print(f"\n🎨 Color Patterns:")
        print(f"  Red: {cp['red_percentage']:.1%} | Black: {cp['black_percentage']:.1%}")
    
    return patterns


def demo_3_pattern_analysis(repo):
    """Demo 3: Analyze patterns across all sessions"""
    print("\n" + "="*70)
    print("DEMO 3: Pattern Analysis Across Sessions")
    print("="*70)
    
    analyzer = PatternAnalyzer(repo)
    
    # Get session performance
    perf = analyzer.get_session_performance_insights()
    print(f"\n📈 Session Performance:")
    print(f"  Total Sessions: {perf['total_sessions']}")
    print(f"  Total Spins: {perf['total_spins']}")
    print(f"  Total Profit: ${perf['total_profit']:.2f}")
    print(f"  Average ROI: {perf['average_roi']:.1%}")
    print(f"  Winning Sessions: {perf['winning_sessions']}")
    print(f"  Losing Sessions: {perf['losing_sessions']}")
    
    # Get hot/cold numbers
    hottest = analyzer.get_hottest_numbers(window_sessions=1)
    coldest = analyzer.get_coldest_numbers(window_sessions=1)
    
    print(f"\n🔥 Hottest Numbers (last session):")
    for num, hits, freq in hottest[:5]:
        print(f"  {num}: {freq:.1%} ({hits} hits)")
    
    print(f"\n❄️  Coldest Numbers (last session):")
    for num, hits, freq in coldest[:5]:
        print(f"  {num}: {freq:.1%} ({hits} hits)")
    
    # Database stats
    stats = repo.get_database_stats()
    print(f"\n💾 Database Statistics:")
    print(f"  Total Sessions: {stats['total_sessions']}")
    print(f"  Total Spins: {stats['total_spins']}")
    print(f"  Total Patterns Detected: {stats['total_patterns_detected']}")
    
    return analyzer


def demo_4_recommendations(spin_results, analyzer):
    """Demo 4: Generate betting recommendations"""
    print("\n" + "="*70)
    print("DEMO 4: AI Betting Recommendations")
    print("="*70)
    
    detector = PatternDetector(GRUPOS_MAESTROS, WHEEL_NEIGHBORS)
    recommender = RecommendationEngine(detector, analyzer, GRUPOS_MAESTROS)
    
    # Generate recommendations for next spin
    recommendations = recommender.generate_spin_recommendations(spin_results, confidence_threshold=0.4)
    
    if not recommendations:
        print("\n⚠️  No recommendations generated (need more spin history)")
        return
    
    print(f"\n💡 Recommendations for Next Spin ({len(recommendations)} found):")
    for i, rec in enumerate(recommendations[:5], 1):
        print(f"\n  {i}. {rec['type'].upper()}: {rec['target']}")
        print(f"     Confidence: {rec['confidence']:.0%}")
        print(f"     Reason: {rec['reason']}")
        print(f"     Bet Type: {rec['bet_type']}")
    
    # Get optimal combination
    optimal = recommender.get_optimal_bet_combination(recommendations)
    bets_list = optimal.get('recommended_bets', []) or optimal.get('bets', [])
    print(f"\n✨ Optimal Bet Combination ({len(bets_list)} bets):")
    if bets_list:
        for bet in bets_list:
            print(f"  • {bet['target']}: {bet['reason']} ({bet['confidence']:.0%})")
    else:
        print("  (None)")
    
    # Get historical insights
    if recommendations:
        target = recommendations[0]['target']
        insights = recommender.get_historical_insights_for_bet(target)
        print(f"\n📊 Historical Insights for {target}:")
        print(f"  Status: {insights.get('status', 'N/A')}")
        print(f"  Recommendation: {insights.get('recommendation', 'N/A')}")


def demo_5_comprehensive_report(analyzer):
    """Demo 5: Generate comprehensive AI report"""
    print("\n" + "="*70)
    print("DEMO 5: Comprehensive AI Report")
    print("="*70)
    
    report = analyzer.generate_comprehensive_report()
    
    print(f"\n📋 Report Generated: {report['generated_at']}")
    
    print(f"\n📊 Performance Summary:")
    perf = report['performance']
    print(f"  Sessions: {perf['total_sessions']}")
    print(f"  Avg ROI: {perf['average_roi']:.1%}")
    print(f"  Best ROI: {perf['best_roi']:.1%}")
    print(f"  Total Profit: ${perf['total_profit']:.2f}")
    
    print(f"\n🔝 Top 5 Prevalent Patterns:")
    for pattern in report['prevalent_patterns'][:5]:
        print(f"  • {pattern['pattern_type']}: {pattern['occurrences']} occurrences " +
              f"(confidence: {pattern['average_confidence']:.0%})")
    
    print(f"\n🔥 Top 5 Hottest Numbers:")
    for num, hits, freq in report['hottest_numbers'][:5]:
        print(f"  • {num}: {freq:.1%}")
    
    print(f"\n👥 Top 3 Best Performing Groups:")
    for group in report['best_groups'][:3]:
        print(f"  • {group['group']}: {group['win_rate']:.0%} win rate " +
              f"({group['wins']} wins, {group['losses']} losses)")


def demo_6_pattern_storage(repo, detector, spin_results):
    """Demo 6: Store detected patterns in database"""
    print("\n" + "="*70)
    print("DEMO 6: Storing Patterns in Database")
    print("="*70)
    
    # Detect patterns
    patterns = detector.analyze_all_patterns(spin_results, ROJOS)
    
    # Save patterns to database
    saved_count = 0
    for pattern_type, pattern_data in patterns['patterns'].items():
        if isinstance(pattern_data, list):
            for p in pattern_data[:3]:  # Save top 3 of each type
                confidence = p.get('confidence', 0.5)
                repo.save_detected_pattern("demo_session_001", pattern_type, p, confidence)
                saved_count += 1
        else:
            confidence = pattern_data.get('confidence', 0.5)
            repo.save_detected_pattern("demo_session_001", pattern_type, pattern_data, confidence)
            saved_count += 1
    
    print(f"✓ Saved {saved_count} patterns to database")
    
    # Retrieve patterns
    all_patterns = repo.get_all_patterns()
    print(f"✓ Retrieved {len(all_patterns)} patterns from database")
    
    if all_patterns:
        print(f"\nSample patterns:")
        for pattern in all_patterns[:3]:
            print(f"  • {pattern['pattern_type']}: confidence {pattern['confidence']:.0%}")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    print("\n" + "="*70)
    print("LINUPAI - AI MODULE DEMONSTRATION")
    print("="*70)
    
    try:
        # Run all demos
        repo, spin_results = demo_1_session_creation()
        patterns = demo_2_pattern_detection(spin_results)
        analyzer = demo_3_pattern_analysis(repo)
        demo_4_recommendations(spin_results, analyzer)
        demo_5_comprehensive_report(analyzer)
        demo_6_pattern_storage(repo, PatternDetector(GRUPOS_MAESTROS, WHEEL_NEIGHBORS), spin_results)
        
        print("\n" + "="*70)
        print("✅ ALL DEMOS COMPLETED SUCCESSFULLY!")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
