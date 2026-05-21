"""
AI Analysis Module - Statistical analysis of patterns across all sessions
Identifies prevalent patterns and generates insights
"""

from typing import List, Dict, Tuple, Optional
from collections import Counter
import json
import statistics
from datetime import datetime

class PatternAnalyzer:
    """Analyzes patterns across multiple sessions to identify dominant trends"""
    
    def __init__(self, session_repository):
        """
        Initialize analyzer with session repository
        
        Args:
            session_repository: SessionRepository instance for data access
        """
        self.repo = session_repository
    
    def get_most_prevalent_patterns(self, limit: int = 20) -> List[Dict]:
        """
        Get the most frequently occurring patterns across all sessions
        
        Args:
            limit: Maximum number of patterns to return
            
        Returns:
            List of patterns sorted by prevalence
        """
        all_patterns = self.repo.get_all_patterns()
        
        if not all_patterns:
            return []
        
        # Group patterns by type and content
        pattern_occurrences = Counter()
        pattern_details = {}
        
        for pattern in all_patterns:
            pattern_type = pattern['pattern_type']
            pattern_data = json.loads(pattern['pattern_data']) if isinstance(pattern['pattern_data'], str) else pattern['pattern_data']
            
            # Create a unique key for the pattern
            if pattern_type == 'group_clustering':
                key = f"group_{pattern_data.get('group', 'unknown')}"
            elif pattern_type == 'number_frequency':
                key = 'number_frequency'
            elif pattern_type == 'repeating_sequence':
                key = f"seq_{tuple(pattern_data.get('sequence', []))}"
            else:
                key = pattern_type
            
            pattern_occurrences[key] += 1
            
            if key not in pattern_details:
                pattern_details[key] = {
                    'type': pattern_type,
                    'data': pattern_data,
                    'avg_confidence': pattern['confidence']
                }
            else:
                # Update average confidence
                pattern_details[key]['avg_confidence'] = (
                    (pattern_details[key]['avg_confidence'] + pattern['confidence']) / 2
                )
        
        # Sort by occurrence count
        prevalent = []
        for pattern_key in sorted(pattern_occurrences.keys(), 
                                  key=lambda k: pattern_occurrences[k], 
                                  reverse=True)[:limit]:
            details = pattern_details[pattern_key]
            prevalent.append({
                'pattern_key': pattern_key,
                'pattern_type': details['type'],
                'occurrences': pattern_occurrences[pattern_key],
                'average_confidence': details['avg_confidence'],
                'data': details['data']
            })
        
        return prevalent
    
    def get_session_performance_insights(self) -> Dict:
        """
        Analyze session performance metrics
        
        Returns:
            Dictionary with performance insights
        """
        all_sessions = self.repo.get_all_sessions()
        
        if not all_sessions:
            return {
                'total_sessions': 0,
                'message': 'No sessions recorded yet'
            }
        
        rois = [s['roi'] for s in all_sessions if s['roi'] is not None]
        profits = [s['ending_capital'] - s['starting_capital'] for s in all_sessions]
        
        insights = {
            'total_sessions': len(all_sessions),
            'total_spins': sum(s['total_spins'] for s in all_sessions),
            'total_profit': sum(profits),
            'average_roi': statistics.mean(rois) if rois else 0,
            'median_roi': statistics.median(rois) if rois else 0,
            'best_roi': max(rois) if rois else 0,
            'worst_roi': min(rois) if rois else 0,
            'winning_sessions': sum(1 for p in profits if p > 0),
            'losing_sessions': sum(1 for p in profits if p < 0),
            'breakeven_sessions': sum(1 for p in profits if p == 0),
        }
        
        if rois:
            insights['roi_std_dev'] = statistics.stdev(rois) if len(rois) > 1 else 0
        
        return insights
    
    def get_hottest_numbers(self, window_sessions: int = 10) -> List[Tuple[int, int, float]]:
        """
        Get the most frequently hit numbers in recent sessions
        
        Args:
            window_sessions: Number of recent sessions to analyze
            
        Returns:
            List of (number, hit_count, frequency) tuples, sorted by frequency
        """
        all_sessions = self.repo.get_all_sessions()
        
        if not all_sessions:
            return []
        
        # Get recent sessions
        recent_sessions = all_sessions[:window_sessions]
        
        number_hits = Counter()
        total_spins = 0
        
        for session_info in recent_sessions:
            session = self.repo.get_session(session_info['session_id'])
            if session:
                for spin in session.spins:
                    number_hits[spin.result] += 1
                    total_spins += 1
        
        if total_spins == 0:
            return []
        
        # Calculate frequencies
        hottest = []
        for number, hits in number_hits.most_common(20):
            frequency = hits / total_spins
            hottest.append((number, hits, frequency))
        
        return hottest
    
    def get_coldest_numbers(self, window_sessions: int = 10) -> List[Tuple[int, int, float]]:
        """
        Get the least frequently hit numbers in recent sessions
        
        Args:
            window_sessions: Number of recent sessions to analyze
            
        Returns:
            List of (number, hit_count, frequency) tuples, sorted by rarity
        """
        all_sessions = self.repo.get_all_sessions()
        
        if not all_sessions:
            return []
        
        # Get recent sessions
        recent_sessions = all_sessions[:window_sessions]
        
        number_hits = Counter()
        total_spins = 0
        
        # Initialize all numbers
        for i in range(37):
            number_hits[i] = 0
        
        for session_info in recent_sessions:
            session = self.repo.get_session(session_info['session_id'])
            if session:
                for spin in session.spins:
                    number_hits[spin.result] += 1
                    total_spins += 1
        
        if total_spins == 0:
            return []
        
        # Calculate frequencies
        coldest = []
        for number, hits in sorted(number_hits.items(), key=lambda x: x[1])[:20]:
            frequency = hits / total_spins
            coldest.append((number, hits, frequency))
        
        return coldest
    
    def get_best_performing_groups(self, window_sessions: int = 10) -> List[Dict]:
        """
        Identify which groups have performed best recently
        
        Args:
            window_sessions: Number of recent sessions to analyze
            
        Returns:
            List of group performance data, sorted by win rate
        """
        all_sessions = self.repo.get_all_sessions()
        
        if not all_sessions:
            return []
        
        recent_sessions = all_sessions[:window_sessions]
        
        group_stats = {}
        
        for session_info in recent_sessions:
            session = self.repo.get_session(session_info['session_id'])
            if session and session.groups_used:
                for group_name in session.groups_used:
                    if group_name not in group_stats:
                        group_stats[group_name] = {
                            'wins': 0,
                            'losses': 0,
                            'times_used': 0
                        }
                    
                    # Count wins for this group
                    for spin in session.spins:
                        for bet in spin.bets:
                            if bet.bet_id == group_name:
                                group_stats[group_name]['times_used'] += 1
                                if bet.result == 'win':
                                    group_stats[group_name]['wins'] += 1
                                elif bet.result == 'loss':
                                    group_stats[group_name]['losses'] += 1
        
        # Calculate win rates
        results = []
        for group_name, stats in group_stats.items():
            total_bets = stats['wins'] + stats['losses']
            if total_bets > 0:
                win_rate = stats['wins'] / total_bets
                results.append({
                    'group': group_name,
                    'wins': stats['wins'],
                    'losses': stats['losses'],
                    'total_bets': total_bets,
                    'win_rate': win_rate
                })
        
        # Sort by win rate descending
        results.sort(key=lambda x: x['win_rate'], reverse=True)
        
        return results
    
    def get_pattern_correlations(self) -> Dict[str, List[str]]:
        """
        Identify which patterns tend to appear together
        
        Returns:
            Dictionary mapping pattern types to commonly co-occurring patterns
        """
        all_sessions = self.repo.get_all_sessions()
        
        if not all_sessions:
            return {}
        
        session_patterns = {}
        
        # Collect patterns by session
        for session_info in all_sessions:
            session_patterns[session_info['session_id']] = {}
        
        all_patterns = self.repo.get_all_patterns()
        
        for pattern in all_patterns:
            session_id = pattern['session_id']
            pattern_type = pattern['pattern_type']
            
            if session_id not in session_patterns:
                session_patterns[session_id] = {}
            
            if pattern_type not in session_patterns[session_id]:
                session_patterns[session_id][pattern_type] = 0
            
            session_patterns[session_id][pattern_type] += 1
        
        # Calculate co-occurrence
        correlations = {}
        
        for session_patterns_dict in session_patterns.values():
            pattern_types = list(session_patterns_dict.keys())
            
            for i, type1 in enumerate(pattern_types):
                if type1 not in correlations:
                    correlations[type1] = Counter()
                
                for type2 in pattern_types[i+1:]:
                    correlations[type1][type2] += 1
        
        # Format results
        result = {}
        for pattern_type, co_patterns in correlations.items():
            result[pattern_type] = [
                f"{ptype} ({count})" 
                for ptype, count in co_patterns.most_common(5)
            ]
        
        return result
    
    def generate_comprehensive_report(self) -> Dict:
        """
        Generate a comprehensive analysis report
        
        Returns:
            Dictionary with complete analysis
        """
        return {
            'generated_at': datetime.now().isoformat(),
            'performance': self.get_session_performance_insights(),
            'prevalent_patterns': self.get_most_prevalent_patterns(limit=15),
            'hottest_numbers': self.get_hottest_numbers(),
            'coldest_numbers': self.get_coldest_numbers(),
            'best_groups': self.get_best_performing_groups(),
            'pattern_correlations': self.get_pattern_correlations(),
            'database_stats': self.repo.get_database_stats()
        }
