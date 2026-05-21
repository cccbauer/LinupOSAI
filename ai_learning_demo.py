"""
AI Learning System Demo - Shows how the learning system works
"""

from ai_sessions import SessionRepository
from ai_patterns import PatternDetector
from ai_analysis import PatternAnalyzer
from ai_recommendations import RecommendationEngine
from ai_decision_tracker import DecisionTracker, Decision, DecisionOutcome
from ai_learning_engine import LearningEngine
from ai_adaptive_recommender import AdaptiveRecommender
from datetime import datetime, timedelta
import random

# ============================================================================
# GROUP DEFINITIONS (from main.py)
# ============================================================================

ROJOS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

GRUPOS_MAESTROS = {
    '34': {1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34},
    '35': {2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35},
    '36': {3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36},
    'R': ROJOS,
    'B': set(range(1, 37)) - ROJOS,
}

WHEEL_ORDER = [0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26]
WHEEL_NEIGHBORS = {
    n: {WHEEL_ORDER[(i - 1) % 37], WHEEL_ORDER[(i + 1) % 37]}
    for i, n in enumerate(WHEEL_ORDER)
}

# ============================================================================
# DEMO FUNCTIONS
# ============================================================================

def demo_1_decision_tracking():
    """Demo 1: Track player decisions"""
    print("\n" + "="*70)
    print("DEMO 1: Decision Tracking")
    print("="*70)
    
    tracker = DecisionTracker("demo_learning.db")
    
    # Create sample decisions with outcomes
    session_id = "learning_session_001"
    decisions_to_make = [
        # Good decisions (player's strengths)
        {'target': '34', 'type': 'group', 'amount': 10, 'source': 'manual', 'result': True},
        {'target': '34', 'type': 'group', 'amount': 10, 'source': 'manual', 'result': True},
        {'target': '34', 'type': 'group', 'amount': 10, 'source': 'manual', 'result': True},
        
        # AI recommendations work well
        {'target': 'R', 'type': 'group', 'amount': 5, 'source': 'ai_recommendation', 'result': True},
        {'target': 'R', 'type': 'group', 'amount': 5, 'source': 'ai_recommendation', 'result': True},
        
        # Mixed results
        {'target': '14', 'type': 'number', 'amount': 20, 'source': 'manual', 'result': False},
        {'target': '14', 'type': 'number', 'amount': 20, 'source': 'manual', 'result': True},
    ]
    
    for i, dec in enumerate(decisions_to_make, 1):
        decision = Decision(
            decision_id=f"dec_{i:03d}",
            session_id=session_id,
            spin_number=i,
            bet_target=dec['target'],
            bet_type=dec['type'],
            bet_amount=dec['amount'],
            decision_context={
                'confidence': 0.7 if dec['result'] else 0.4,
                'reason': 'Test decision',
                'patterns_detected': 1
            },
            source=dec['source'],
            decision_time=datetime.now() - timedelta(hours=7-i),
            spin_result=random.randint(1, 36),
            outcome='win' if dec['result'] else 'loss',
            profit_loss=dec['amount'] if dec['result'] else -dec['amount'],
            player_satisfaction=5 if dec['result'] else 2
        )
        
        tracker.record_decision(decision)
    
    print(f"✓ Recorded {len(decisions_to_make)} decisions")
    
    # Get stats
    stats = tracker.get_decision_stats()
    print(f"\nDecision Statistics:")
    print(f"  Total Decisions: {stats['total_decisions']}")
    print(f"  Win Rate: {stats['win_rate']:.0%}")
    print(f"  Total Profit: ${stats['total_profit']:.2f}")
    print(f"  Sources: {stats['decision_sources']}")
    
    return tracker


def demo_2_learning_engine(tracker):
    """Demo 2: Learn from decisions"""
    print("\n" + "="*70)
    print("DEMO 2: Learning Engine")
    print("="*70)
    
    learner = LearningEngine(tracker)
    
    # Analyze decision patterns
    print("\n📊 Decision Pattern Analysis:")
    patterns = learner.analyze_decision_patterns()
    
    if patterns.get('status') == 'analysis_complete':
        print(f"  Total Decisions Analyzed: {patterns['total_decisions_analyzed']}")
        print(f"  Best Targets:")
        for target in patterns['best_targets'][:3]:
            print(f"    • {target['bet_target']}: {target['win_rate']:.0%} win rate " +
                  f"(${target['average_profit']:.2f} avg profit)")
    
    # Identify player style
    print("\n🎯 Player Style Analysis:")
    style = learner.identify_player_style()
    print(f"  AI Alignment: {style.get('ai_alignment', 'UNKNOWN')}")
    print(f"  Preferred Bet Types: {style.get('preferred_bet_types', {})}")
    print(f"  Favorite Targets: {list(style.get('favorite_targets', {}).keys())[:3]}")
    
    # Learn winning patterns
    print("\n🏆 Learned Winning Patterns:")
    learned = learner.learn_winning_patterns()
    if learned:
        for i, pattern in enumerate(learned[:3], 1):
            print(f"  {i}. Pattern: {pattern['pattern_key']}")
            print(f"     Win Rate: {pattern['win_rate']:.0%} ({pattern['total_occurrences']} times)")
            print(f"     Confidence: {pattern['confidence']:.0%}")
    else:
        print("  No winning patterns learned yet (need more data)")
    
    # Get player profile
    print("\n👤 Complete Player Profile:")
    profile = learner.get_player_profile()
    summary = profile['profile_summary']
    print(f"  Total Decisions: {summary['total_decisions']}")
    print(f"  Overall Win Rate: {summary['overall_win_rate']:.0%}")
    print(f"  Total Profit: ${summary['total_profit']:.2f}")
    print(f"  Best Bet Target: {summary['best_bet_target']}")
    
    return learner


def demo_3_adaptive_recommendations(tracker, learner):
    """Demo 3: Generate adaptive recommendations"""
    print("\n" + "="*70)
    print("DEMO 3: Adaptive Recommendations")
    print("="*70)
    
    # Initialize components
    detector = PatternDetector(GRUPOS_MAESTROS, WHEEL_NEIGHBORS)
    repo = SessionRepository("demo_learning.db")
    analyzer = PatternAnalyzer(repo)
    base_recommender = RecommendationEngine(detector, analyzer, GRUPOS_MAESTROS)
    adaptive = AdaptiveRecommender(base_recommender, learner, tracker)
    
    # Get learned best bets
    print("\n🎲 Your Learned Best Bets:")
    best_bets = adaptive.get_learned_best_bets()
    for bet in best_bets[:3]:
        print(f"  • {bet['target']}: {bet['win_rate']:.0%} win rate " +
              f"({bet['total_bets']} bets, ${bet['average_profit']:.2f} avg profit)")
    
    # Get bets to avoid
    print("\n⚠️  Bets to Avoid:")
    avoid = adaptive.get_decisions_to_avoid()
    if avoid:
        for bet in avoid[:2]:
            print(f"  • {bet['target']}: {bet['win_rate']:.0%} win rate ({bet['total_bets']} bets)")
    else:
        print("  No consistent losers yet")
    
    # Get betting style recommendations
    print("\n💡 Betting Style Recommendations:")
    style_recs = adaptive.get_betting_style_recommendations()
    print(f"  Frequency: {style_recs['betting_frequency']}")
    print(f"  Bet Sizing: {style_recs['bet_sizing']}")
    print(f"  AI Usage: {style_recs['ai_usage']}")
    print(f"  Risk Level: {style_recs['risk_level']}")
    if style_recs['focus_areas']:
        print(f"  Focus: {style_recs['focus_areas'][0]}")
    
    # Get improvement tips
    print("\n📈 Improvement Tips:")
    tips = learner.get_decision_improvement_tips()
    for tip in tips[:3]:
        print(f"  • {tip}")
    
    return adaptive


def demo_4_recommendation_evaluation(tracker, adaptive):
    """Demo 4: Evaluate specific recommendations"""
    print("\n" + "="*70)
    print("DEMO 4: Recommendation Evaluation")
    print("="*70)
    
    # Test evaluating different recommendations
    test_recommendations = [
        {'target': '34', 'confidence': 0.7, 'reason': 'Group clustering'},
        {'target': 'R', 'confidence': 0.6, 'reason': 'Color pattern'},
        {'target': '14', 'confidence': 0.5, 'reason': 'Hot number'},
    ]
    
    print("\nEvaluating Recommendations Against Your History:")
    for rec in test_recommendations:
        evaluation = adaptive.should_accept_recommendation(rec)
        print(f"\n  Recommendation: Bet {rec['target']} (AI confidence: {rec['confidence']:.0%})")
        print(f"    Your History: {evaluation['reason']}")
        print(f"    Recommendation: {evaluation['recommendation']}")
        print(f"    Adjusted Confidence: {evaluation['confidence']:.0%}")


def demo_5_player_comparison(tracker, learner):
    """Demo 5: Compare manual vs AI performance"""
    print("\n" + "="*70)
    print("DEMO 5: Manual vs AI Comparison")
    print("="*70)
    
    manual_decisions = tracker.get_decisions_by_source('manual', limit=100)
    ai_decisions = tracker.get_decisions_by_source('ai_recommendation', limit=100)
    
    if not manual_decisions or not ai_decisions:
        print("Not enough decisions to compare")
        return
    
    comparison = learner.compare_decision_quality(manual_decisions, ai_decisions)
    
    print("\n📊 Performance Comparison:")
    print(f"  Manual Decisions:")
    print(f"    Win Rate: {comparison['manual_performance']['win_rate']:.0%}")
    print(f"    Total Profit: ${comparison['manual_performance']['total_profit']:.2f}")
    
    print(f"\n  AI Recommendations:")
    print(f"    Win Rate: {comparison['ai_performance']['win_rate']:.0%}")
    print(f"    Total Profit: ${comparison['ai_performance']['total_profit']:.2f}")
    
    print(f"\n  AI Advantage: {comparison['ai_advantage']:+.0%}")
    print(f"  Recommendation: {comparison['recommendation']}")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    print("\n" + "="*70)
    print("LINUPAI - LEARNING SYSTEM DEMONSTRATION")
    print("="*70)
    
    try:
        # Run all demos
        tracker = demo_1_decision_tracking()
        learner = demo_2_learning_engine(tracker)
        adaptive = demo_3_adaptive_recommendations(tracker, learner)
        demo_4_recommendation_evaluation(tracker, adaptive)
        demo_5_player_comparison(tracker, learner)
        
        print("\n" + "="*70)
        print("✅ ALL LEARNING DEMOS COMPLETED SUCCESSFULLY!")
        print("="*70)
        print("\nThe learning system is now:")
        print("  ✓ Tracking all your decisions")
        print("  ✓ Learning from wins and losses")
        print("  ✓ Building your player profile")
        print("  ✓ Providing personalized recommendations")
        print("  ✓ Giving improvement suggestions")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
