"""
AI Recommendations Module - Generate betting recommendations based on patterns
Suggests optimal bets leveraging detected patterns and historical data
"""

from typing import List, Dict, Tuple, Optional
from datetime import datetime
import json

class RecommendationEngine:
    """Generates intelligent betting recommendations based on pattern analysis"""
    
    def __init__(self, pattern_detector, pattern_analyzer, grupos_maestros: Dict):
        """
        Initialize recommendation engine
        
        Args:
            pattern_detector: PatternDetector instance
            pattern_analyzer: PatternAnalyzer instance
            grupos_maestros: Group definitions
        """
        self.detector = pattern_detector
        self.analyzer = pattern_analyzer
        self.grupos = grupos_maestros
    
    def generate_spin_recommendations(self, recent_spins: List[int], 
                                     confidence_threshold: float = 0.4) -> List[Dict]:
        """
        Generate betting recommendations for the next spin
        
        Args:
            recent_spins: List of recent winning numbers
            confidence_threshold: Minimum confidence score to include recommendation
            
        Returns:
            List of recommended bets with confidence scores
        """
        recommendations = []
        
        if len(recent_spins) < 5:
            return []  # Need enough history
        
        # Analyze current patterns
        patterns = self.detector.analyze_all_patterns(recent_spins, self.detector.grupos.get('R', set()))
        
        # 1. Hot number recommendations
        if 'number_frequency' in patterns:
            hot_nums = patterns['number_frequency'].get('hot_numbers', {})
            for num, frequency in sorted(hot_nums.items(), key=lambda x: x[1], reverse=True)[:5]:
                confidence = min(0.9, frequency * 2)  # Hot numbers are confidence-weighted
                if confidence >= confidence_threshold:
                    recommendations.append({
                        'type': 'number',
                        'target': str(num),
                        'reason': f'Hot number (frequency: {frequency:.1%})',
                        'confidence': confidence,
                        'bet_type': 'inside',
                        'priority': 1
                    })
        
        # 2. Hot group recommendations
        if 'group_clustering' in patterns:
            for group_pattern in patterns['group_clustering'][:3]:
                if group_pattern.get('confidence', 0) >= confidence_threshold:
                    recommendations.append({
                        'type': 'group',
                        'target': group_pattern['group'],
                        'reason': f'Group clustering (deviation: {group_pattern["deviation"]:.1%})',
                        'confidence': group_pattern['confidence'],
                        'bet_type': 'outside',
                        'priority': 2
                    })
        
        # 3. Neighbor recommendations
        if 'neighbor_clustering' in patterns:
            neighbor_data = patterns['neighbor_clustering']
            if neighbor_data.get('confidence', 0) >= confidence_threshold:
                # Recommend betting on groups that include high-appearing neighbors
                recommendations.append({
                    'type': 'pattern',
                    'target': 'wheel_neighbors',
                    'reason': f'Neighbor clustering pattern detected',
                    'confidence': neighbor_data['confidence'],
                    'bet_type': 'inside',
                    'priority': 3
                })
        
        # 4. Repeating sequence recommendations
        if 'repeating_sequences' in patterns and patterns['repeating_sequences']:
            for seq_pattern in patterns['repeating_sequences'][:2]:
                if seq_pattern.get('confidence', 0) >= confidence_threshold:
                    next_in_sequence = seq_pattern['sequence'][-1]  # Last number in sequence
                    recommendations.append({
                        'type': 'sequence',
                        'target': str(next_in_sequence),
                        'reason': f'Repeating sequence pattern (occ: {seq_pattern["occurrences"]})',
                        'confidence': seq_pattern['confidence'],
                        'bet_type': 'inside',
                        'priority': 4
                    })
        
        # 5. Color trend recommendations
        if 'color_patterns' in patterns:
            color_data = patterns['color_patterns']
            red_pct = color_data.get('red_percentage', 0.5)
            
            # If one color is significantly dominant
            if red_pct > 0.6:
                recommendations.append({
                    'type': 'color',
                    'target': 'R',
                    'reason': f'Red color trend ({red_pct:.0%})',
                    'confidence': min(0.7, red_pct - 0.5),
                    'bet_type': 'outside',
                    'priority': 5
                })
            elif red_pct < 0.4:
                recommendations.append({
                    'type': 'color',
                    'target': 'B',
                    'reason': f'Black color trend ({100-red_pct:.0%})',
                    'confidence': min(0.7, 0.5 - red_pct),
                    'bet_type': 'outside',
                    'priority': 5
                })
        
        # Sort by confidence
        recommendations.sort(key=lambda x: (-x['confidence'], x['priority']))
        
        return recommendations
    
    def get_optimal_bet_combination(self, recommendations: List[Dict]) -> Dict:
        """
        Suggest an optimal combination of bets from recommendations
        
        Args:
            recommendations: List of recommendations from generate_spin_recommendations
            
        Returns:
            Dictionary with suggested bet combination
        """
        if not recommendations:
            return {'status': 'no_recommendations', 'bets': []}
        
        # Combine top high-confidence recommendations
        selected_bets = []
        total_coverage = set()
        
        for rec in recommendations[:5]:  # Take top 5 recommendations
            if rec['confidence'] >= 0.5:  # Only select confident recommendations
                selected_bets.append({
                    'target': rec['target'],
                    'type': rec['type'],
                    'reason': rec['reason'],
                    'confidence': rec['confidence']
                })
        
        return {
            'status': 'recommendations_generated',
            'recommended_bets': selected_bets,
            'recommendation_count': len(selected_bets),
            'generated_at': datetime.now().isoformat()
        }
    
    def get_historical_insights_for_bet(self, bet_id: str) -> Dict:
        """
        Get historical performance data for a specific bet
        
        Args:
            bet_id: The bet identifier (group name, number, etc.)
            
        Returns:
            Dictionary with historical insights
        """
        try:
            best_groups = self.analyzer.get_best_performing_groups(window_sessions=20)
            
            # Find this group in the results
            group_info = next((g for g in best_groups if g['group'] == bet_id), None)
            
            if group_info:
                return {
                    'bet': bet_id,
                    'type': 'group',
                    'win_rate': group_info['win_rate'],
                    'wins': group_info['wins'],
                    'losses': group_info['losses'],
                    'total_bets': group_info['total_bets'],
                    'recommendation': 'STRONG' if group_info['win_rate'] > 0.6 else 
                                    'MODERATE' if group_info['win_rate'] > 0.5 else 
                                    'WEAK'
                }
            
            # Check if it's a number (hot/cold analysis)
            try:
                num = int(bet_id)
                hottest = self.analyzer.get_hottest_numbers(window_sessions=20)
                coldest = self.analyzer.get_coldest_numbers(window_sessions=20)
                
                hottest_nums = {h[0] for h in hottest}
                coldest_nums = {c[0] for c in coldest}
                
                if num in hottest_nums:
                    hit_data = next(h for h in hottest if h[0] == num)
                    return {
                        'bet': bet_id,
                        'type': 'number',
                        'status': 'hot',
                        'hits': hit_data[1],
                        'frequency': hit_data[2],
                        'recommendation': 'STRONG'
                    }
                elif num in coldest_nums:
                    hit_data = next(c for c in coldest if c[0] == num)
                    return {
                        'bet': bet_id,
                        'type': 'number',
                        'status': 'cold',
                        'hits': hit_data[1],
                        'frequency': hit_data[2],
                        'recommendation': 'WEAK'
                    }
            except ValueError:
                pass
            
            return {'bet': bet_id, 'status': 'no_data', 'recommendation': 'NEUTRAL'}
        
        except Exception as e:
            print(f"Error getting insights for bet {bet_id}: {e}")
            return {'bet': bet_id, 'status': 'error', 'recommendation': 'SKIP'}
    
    def suggest_progression_adjustment(self, session_roi: float, 
                                      recent_performance: List[float]) -> Dict:
        """
        Suggest progression strategy adjustments based on performance
        
        Args:
            session_roi: Current session ROI
            recent_performance: List of recent session ROI values
            
        Returns:
            Dictionary with progression suggestions
        """
        avg_recent_roi = sum(recent_performance) / len(recent_performance) if recent_performance else 0
        
        suggestion = {
            'current_roi': session_roi,
            'recent_avg_roi': avg_recent_roi,
            'adjustment': 'NONE',
            'reason': ''
        }
        
        if session_roi > 0.2 and avg_recent_roi > 0.15:
            suggestion['adjustment'] = 'INCREASE'
            suggestion['reason'] = 'Strong recent performance - consider increasing bet sizes'
        elif session_roi < -0.2 and avg_recent_roi < -0.15:
            suggestion['adjustment'] = 'DECREASE'
            suggestion['reason'] = 'Recent losses - consider reducing bet sizes'
        elif session_roi < -0.05:
            suggestion['adjustment'] = 'RESET'
            suggestion['reason'] = 'Small loss - consider resetting progression'
        else:
            suggestion['adjustment'] = 'MAINTAIN'
            suggestion['reason'] = 'Performance stable - maintain current strategy'
        
        return suggestion
    
    def generate_session_forecast(self, spin_history: List[int], 
                                 starting_capital: float,
                                 num_predicted_spins: int = 10) -> Dict:
        """
        Generate a forecast for upcoming spins based on patterns
        
        Args:
            spin_history: Historical spin results
            starting_capital: Starting betting capital
            num_predicted_spins: Number of spins to forecast
            
        Returns:
            Dictionary with forecast data
        """
        recommendations = self.generate_spin_recommendations(spin_history)
        
        if not recommendations:
            return {
                'status': 'insufficient_data',
                'message': 'Need more spin history to generate forecast'
            }
        
        # Estimate expected outcomes based on top recommendations
        top_rec = recommendations[0] if recommendations else None
        
        if not top_rec:
            return {'status': 'no_recommendations'}
        
        # Simulate outcomes
        forecast_capital = starting_capital
        forecasted_spins = []
        
        for i in range(num_predicted_spins):
            # Estimate based on confidence and historical data
            confidence = top_rec['confidence']
            
            # Rough estimate: 50% chance of win when confidence > 0.5
            if confidence > 0.5:
                expected_return = 0.05  # Assume 5% profit per successful spin
                forecast_capital *= (1 + expected_return)
            else:
                forecast_capital *= 0.98  # Assume 2% loss
            
            forecasted_spins.append({
                'spin_number': i + 1,
                'forecasted_capital': forecast_capital,
                'projected_roi': (forecast_capital - starting_capital) / starting_capital
            })
        
        return {
            'status': 'forecast_generated',
            'starting_capital': starting_capital,
            'predicted_spins': num_predicted_spins,
            'forecasted_capital': forecast_capital,
            'projected_roi': (forecast_capital - starting_capital) / starting_capital,
            'confidence': top_rec['confidence'],
            'forecast_data': forecasted_spins
        }
