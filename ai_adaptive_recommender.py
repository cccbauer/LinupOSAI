"""
AI Adaptive Recommender - Learns from your decisions and gives personalized suggestions
Adapts recommendations based on your performance history
"""

from typing import List, Dict, Optional
from datetime import datetime
import statistics

class AdaptiveRecommender:
    """Generates personalized recommendations based on learned player patterns"""
    
    def __init__(self, recommendation_engine, learning_engine, decision_tracker):
        """
        Initialize adaptive recommender
        
        Args:
            recommendation_engine: The main RecommendationEngine instance
            learning_engine: LearningEngine instance
            decision_tracker: DecisionTracker instance
        """
        self.base_recommender = recommendation_engine
        self.learner = learning_engine
        self.tracker = decision_tracker
    
    def get_personalized_recommendations(self, recent_spins: List[int], 
                                        confidence_threshold: float = 0.4) -> List[Dict]:
        """
        Generate recommendations personalized to player's winning style
        
        Args:
            recent_spins: List of recent winning numbers
            confidence_threshold: Minimum confidence for recommendations
            
        Returns:
            List of personalized recommendations
        """
        # Get base AI recommendations
        base_recs = self.base_recommender.generate_spin_recommendations(
            recent_spins, 
            confidence_threshold
        )
        
        # Get player profile
        profile = self.learner.get_player_profile()
        best_targets = profile['performance_analysis'].get('best_targets', [])
        
        # Boost recommendations for player's best targets
        personalized_recs = []
        for rec in base_recs:
            # Check if this target matches player's best targets
            bonus_boost = 0
            for best_target in best_targets[:3]:
                if rec['target'] == best_target['bet_target']:
                    # Boost confidence if it's one of player's best
                    bonus_boost = 0.15 * (1 - best_target['win_rate'])
            
            personalized_rec = rec.copy()
            personalized_rec['confidence'] = min(0.95, rec['confidence'] + bonus_boost)
            personalized_rec['personalized'] = bonus_boost > 0
            
            # Add player history insight
            target_decisions = self.tracker.get_decisions_by_target(rec['target'], limit=20)
            if target_decisions:
                target_wins = sum(1 for d in target_decisions if d['outcome'] == 'win')
                target_win_rate = target_wins / len(target_decisions)
                personalized_rec['your_historical_win_rate'] = target_win_rate
                personalized_rec['your_bets_on_this'] = len(target_decisions)
            
            personalized_recs.append(personalized_rec)
        
        # Sort by personalized confidence
        personalized_recs.sort(key=lambda x: (-x['confidence'], -x.get('your_historical_win_rate', 0)))
        
        return personalized_recs
    
    def get_learned_best_bets(self, limit: int = 10) -> List[Dict]:
        """
        Get the best bets based on player's learned patterns
        
        Returns:
            List of best bets for this player
        """
        profile = self.learner.get_player_profile()
        best_targets = profile['performance_analysis'].get('best_targets', [])
        
        learned_bets = []
        for target_data in best_targets[:limit]:
            learned_bets.append({
                'target': target_data['bet_target'],
                'win_rate': target_data['win_rate'],
                'average_profit': target_data['average_profit'],
                'total_profit': target_data['total_profit'],
                'total_bets': target_data['total_bets'],
                'confidence': target_data['win_rate'],
                'reason': f"Your best bet: {target_data['win_rate']:.0%} win rate from {target_data['total_bets']} bets"
            })
        
        return learned_bets
    
    def get_decisions_to_avoid(self) -> List[Dict]:
        """
        Get betting targets that consistently lose for this player
        
        Returns:
            List of bets to avoid
        """
        profile = self.learner.get_player_profile()
        worst_targets = profile['performance_analysis'].get('worst_targets', [])
        
        avoid_bets = []
        for target_data in worst_targets[:5]:
            if target_data['win_rate'] < 0.45:  # Only if significantly underperforming
                avoid_bets.append({
                    'target': target_data['bet_target'],
                    'win_rate': target_data['win_rate'],
                    'total_bets': target_data['total_bets'],
                    'reason': f"Avoid: Only {target_data['win_rate']:.0%} win rate from {target_data['total_bets']} bets"
                })
        
        return avoid_bets
    
    def should_accept_recommendation(self, recommendation: Dict) -> Dict:
        """
        Evaluate if the player should follow a specific recommendation
        
        Args:
            recommendation: A recommendation to evaluate
            
        Returns:
            Dictionary with decision and reasoning
        """
        target = recommendation['target']
        rec_confidence = recommendation['confidence']
        
        # Check player's history with this target
        target_decisions = self.tracker.get_decisions_by_target(target, limit=30)
        
        if not target_decisions:
            return {
                'should_follow': rec_confidence > 0.6,
                'confidence': rec_confidence,
                'reason': 'No history with this bet',
                'recommendation': 'FOLLOW' if rec_confidence > 0.6 else 'PASS'
            }
        
        # Calculate player's historical performance
        wins = sum(1 for d in target_decisions if d['outcome'] == 'win')
        losses = sum(1 for d in target_decisions if d['outcome'] == 'loss')
        total = wins + losses
        
        if total == 0:
            player_win_rate = 0.5
        else:
            player_win_rate = wins / total
        
        # Decision logic
        if player_win_rate > 0.55:
            # Player is good with this bet
            should_follow = True
            confidence = min(0.95, rec_confidence * (1 + (player_win_rate - 0.5)))
        elif player_win_rate < 0.45:
            # Player struggles with this bet
            should_follow = False
            confidence = rec_confidence * 0.5  # Reduce confidence
        else:
            # Mixed history
            should_follow = rec_confidence > 0.55
            confidence = rec_confidence
        
        return {
            'should_follow': should_follow,
            'confidence': confidence,
            'your_win_rate': player_win_rate,
            'ai_confidence': rec_confidence,
            'your_bets': total,
            'reason': f"Your history: {wins}/{total} wins ({player_win_rate:.0%})",
            'recommendation': 'FOLLOW' if should_follow else 'SKIP'
        }
    
    def get_betting_style_recommendations(self) -> Dict:
        """
        Get recommendations on optimal betting style based on player profile
        
        Returns:
            Dictionary with style recommendations
        """
        profile = self.learner.get_player_profile()
        style = profile['player_style']
        stats = profile['decision_statistics']
        
        recommendations = {
            'betting_frequency': self._recommend_frequency(stats),
            'bet_sizing': self._recommend_bet_sizing(stats),
            'ai_usage': self._recommend_ai_usage(style),
            'focus_areas': self._recommend_focus(profile['performance_analysis']),
            'risk_level': self._recommend_risk_level(stats)
        }
        
        return recommendations
    
    def _recommend_frequency(self, stats: Dict) -> str:
        """Recommend betting frequency"""
        win_rate = stats.get('win_rate', 0)
        total = stats.get('total_decisions', 0)
        
        if total < 20:
            return "Make more bets to build a better profile (need at least 50)"
        elif win_rate > 0.55:
            return "Great performance! Keep betting at current frequency"
        elif win_rate < 0.45:
            return "Consider reducing bet frequency and being more selective"
        else:
            return "Current frequency is working well"
    
    def _recommend_bet_sizing(self, stats: Dict) -> str:
        """Recommend bet sizing strategy"""
        total_profit = stats.get('total_profit', 0)
        total_decisions = stats.get('total_decisions', 0)
        
        if total_profit > 0:
            return "Consider increasing bet size - you're profitable"
        elif total_profit < -100:
            return "Reduce bet size to minimize losses while learning"
        else:
            return "Keep bet sizes consistent and steady"
    
    def _recommend_ai_usage(self, style: Dict) -> str:
        """Recommend AI usage"""
        alignment = style.get('ai_alignment', 'UNKNOWN')
        
        if alignment == 'TRUSTS_AI':
            return "You excel with AI guidance - follow recommendations more often"
        elif alignment == 'TRUSTS_INTUITION':
            return "Your intuition is strong - trust your instincts"
        else:
            return "Mix manual and AI decisions equally"
    
    def _recommend_focus(self, performance: Dict) -> List[str]:
        """Recommend what to focus on"""
        best = performance.get('best_targets', [])
        
        focus = []
        if best:
            top_3 = [t['bet_target'] for t in best[:3]]
            focus.append(f"Focus on your best bets: {', '.join(top_3)}")
        
        return focus
    
    def _recommend_risk_level(self, stats: Dict) -> str:
        """Recommend risk level"""
        win_rate = stats.get('win_rate', 0)
        
        if win_rate > 0.60:
            return "AGGRESSIVE - You can take more risks"
        elif win_rate > 0.52:
            return "BALANCED - Current strategy is working"
        elif win_rate > 0.48:
            return "CONSERVATIVE - Reduce risk and be selective"
        else:
            return "VERY_CONSERVATIVE - Focus on high-confidence bets only"
    
    def get_adaptive_confidence(self, recommendation: Dict) -> float:
        """
        Calculate adaptive confidence for a recommendation based on player history
        
        Args:
            recommendation: The recommendation to evaluate
            
        Returns:
            Adjusted confidence score (0-1)
        """
        target = recommendation['target']
        base_confidence = recommendation['confidence']
        
        # Get player's history
        target_decisions = self.tracker.get_decisions_by_target(target, limit=50)
        
        if not target_decisions:
            return base_confidence
        
        # Calculate adjustment
        wins = sum(1 for d in target_decisions if d['outcome'] == 'win')
        total = len(target_decisions)
        
        if total == 0:
            return base_confidence
        
        player_win_rate = wins / total
        expected_rate = 1 / 37  # Expected for random number
        
        # If player does well with this, boost confidence
        if player_win_rate > expected_rate * 1.5:
            boost = 0.15 * (player_win_rate - expected_rate)
            return min(0.95, base_confidence + boost)
        # If player struggles, reduce confidence
        elif player_win_rate < expected_rate * 0.5:
            reduction = 0.2 * (expected_rate - player_win_rate)
            return max(0.1, base_confidence - reduction)
        
        return base_confidence
    
    def generate_next_spin_suggestion(self, recent_spins: List[int]) -> Dict:
        """
        Generate a complete recommendation for the next spin with all context
        
        Args:
            recent_spins: Recent spin results
            
        Returns:
            Complete recommendation with reasoning
        """
        # Get personalized recommendations
        personalized_recs = self.get_personalized_recommendations(recent_spins)
        
        if not personalized_recs:
            return {
                'status': 'no_recommendation',
                'message': 'Insufficient data for recommendation'
            }
        
        # Get the top recommendation
        top_rec = personalized_recs[0]
        
        # Evaluate it
        evaluation = self.should_accept_recommendation(top_rec)
        
        # Build comprehensive suggestion
        suggestion = {
            'status': 'recommendation_ready',
            'suggested_bet': top_rec['target'],
            'confidence': self.get_adaptive_confidence(top_rec),
            'reason': top_rec['reason'],
            'your_history': evaluation['reason'],
            'recommendation_strength': evaluation['recommendation'],
            'alternative_bets': [
                {
                    'target': r['target'],
                    'confidence': self.get_adaptive_confidence(r)
                }
                for r in personalized_recs[1:4]
            ],
            'generated_at': datetime.now().isoformat()
        }
        
        return suggestion
