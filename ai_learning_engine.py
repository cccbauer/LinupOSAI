"""
AI Learning Engine - Learns from player decisions to build player profile
Analyzes what decisions work well and what don't
"""

from typing import List, Dict, Tuple, Optional
from collections import Counter, defaultdict
import hashlib
import json
from datetime import datetime
import statistics
import sqlite3

class LearningEngine:
    """Learns from player decisions and builds adaptive models"""
    
    def __init__(self, decision_tracker):
        """
        Initialize learning engine
        
        Args:
            decision_tracker: DecisionTracker instance for data access
        """
        self.tracker = decision_tracker
    
    def analyze_decision_patterns(self) -> Dict:
        """
        Analyze all decisions to find winning patterns
        
        Returns:
            Dictionary with pattern analysis
        """
        decisions = self.tracker.get_decisions_with_outcomes()
        
        if not decisions:
            return {'status': 'insufficient_data', 'message': 'No decisions with outcomes'}
        
        # Group by bet target
        target_performance = defaultdict(lambda: {'wins': 0, 'losses': 0, 'profits': 0})
        
        for decision in decisions:
            if decision['outcome'] == 'win':
                target_performance[decision['bet_target']]['wins'] += 1
            elif decision['outcome'] == 'loss':
                target_performance[decision['bet_target']]['losses'] += 1
            
            if decision['profit_loss']:
                target_performance[decision['bet_target']]['profits'] += decision['profit_loss']
        
        # Calculate win rates and ROI by target
        results = []
        for target, stats in target_performance.items():
            total = stats['wins'] + stats['losses']
            if total > 0:
                win_rate = stats['wins'] / total
                avg_profit = stats['profits'] / total if total > 0 else 0
                results.append({
                    'bet_target': target,
                    'wins': stats['wins'],
                    'losses': stats['losses'],
                    'total_bets': total,
                    'win_rate': win_rate,
                    'average_profit': avg_profit,
                    'total_profit': stats['profits']
                })
        
        # Sort by win rate
        results.sort(key=lambda x: x['win_rate'], reverse=True)
        
        return {
            'status': 'analysis_complete',
            'total_decisions_analyzed': len(decisions),
            'target_performance': results,
            'best_targets': results[:5] if results else [],
            'worst_targets': results[-5:] if results else []
        }
    
    def identify_player_style(self) -> Dict:
        """
        Identify the player's betting style and preferences
        
        Returns:
            Dictionary describing player's style
        """
        stats = self.tracker.get_decision_stats()
        all_decisions = self.tracker.get_decisions_by_source('manual', limit=1000)
        all_ai_decisions = self.tracker.get_decisions_by_source('ai_recommendation', limit=1000)
        
        if not all_decisions:
            return {'status': 'insufficient_data'}
        
        # Analyze what types of bets player makes
        bet_types = Counter()
        manual_targets = Counter()
        ai_targets = Counter()
        
        for d in all_decisions:
            bet_types[d['bet_type']] += 1
            manual_targets[d['bet_target']] += 1
        
        for d in all_ai_decisions:
            ai_targets[d['bet_target']] += 1
        
        # Check if player follows AI recommendations
        ai_win_rate = (sum(1 for d in all_ai_decisions if d['outcome'] == 'win') / 
                      len(all_ai_decisions)) if all_ai_decisions else 0
        manual_win_rate = (sum(1 for d in all_decisions if d['outcome'] == 'win') / 
                          len(all_decisions)) if all_decisions else 0
        
        # Determine style
        if ai_win_rate > manual_win_rate * 1.2:
            ai_alignment = "TRUSTS_AI"
        elif manual_win_rate > ai_win_rate * 1.2:
            ai_alignment = "TRUSTS_INTUITION"
        else:
            ai_alignment = "BALANCED"
        
        return {
            'status': 'style_identified',
            'total_manual_decisions': len(all_decisions),
            'total_ai_decisions': len(all_ai_decisions),
            'manual_win_rate': manual_win_rate,
            'ai_win_rate': ai_win_rate,
            'ai_alignment': ai_alignment,
            'preferred_bet_types': dict(bet_types.most_common(3)),
            'favorite_targets': dict(manual_targets.most_common(5)),
            'win_rate': stats.get('win_rate', 0),
            'total_profit': stats.get('total_profit', 0)
        }
    
    def extract_context_features(self, decision: Dict) -> Dict:
        """
        Extract features from a decision's context for pattern matching
        
        Args:
            decision: Decision dictionary
            
        Returns:
            Dictionary of extracted features
        """
        context = decision.get('decision_context', {})
        
        features = {
            'bet_target': decision['bet_target'],
            'bet_type': decision['bet_type'],
            'source': decision['source'],
            'confidence': context.get('confidence', 0),
            'reason': context.get('reason', ''),
            'amount_tier': self._classify_amount(decision['bet_amount']),
            'hour_of_day': int(decision['decision_time'][:13].split('T')[1]) if 'T' in decision['decision_time'] else 12,
        }
        
        return features
    
    def _classify_amount(self, amount: float) -> str:
        """Classify bet amount into tier"""
        if amount < 5:
            return 'micro'
        elif amount < 20:
            return 'small'
        elif amount < 50:
            return 'medium'
        else:
            return 'large'
    
    def build_context_hash(self, features: Dict) -> str:
        """Create a hash of decision context for pattern matching"""
        # Focus on key features for context matching
        context_str = f"{features['bet_target']}_{features['bet_type']}_{features['source']}"
        return hashlib.md5(context_str.encode()).hexdigest()[:16]
    
    def learn_winning_patterns(self) -> List[Dict]:
        """
        Learn patterns from winning decisions
        
        Returns:
            List of learned winning patterns
        """
        decisions = self.tracker.get_decisions_with_outcomes()
        
        if not decisions:
            return []
        
        # Group decisions by context
        pattern_groups = defaultdict(lambda: {'wins': 0, 'losses': 0, 'profits': [], 'decisions': []})
        
        for decision in decisions:
            if decision['outcome'] == 'pending':
                continue
            
            features = self.extract_context_features(decision)
            context_hash = self.build_context_hash(features)
            
            group = pattern_groups[context_hash]
            
            if decision['outcome'] == 'win':
                group['wins'] += 1
            elif decision['outcome'] == 'loss':
                group['losses'] += 1
            
            if decision['profit_loss']:
                group['profits'].append(decision['profit_loss'])
            
            group['decisions'].append(features)
        
        # Extract patterns with sufficient data
        patterns = []
        for context_hash, group in pattern_groups.items():
            total = group['wins'] + group['losses']
            
            # Only consider patterns with at least 3 occurrences
            if total >= 3:
                win_rate = group['wins'] / total
                avg_profit = statistics.mean(group['profits']) if group['profits'] else 0
                
                # Only save patterns with >50% win rate
                if win_rate > 0.5:
                    pattern_key = f"{group['decisions'][0]['bet_target']}_{group['decisions'][0]['source']}"
                    
                    # Save to database
                    self.tracker.save_learned_pattern(
                        pattern_key,
                        context_hash,
                        group['decisions'][0],
                        group['wins'],
                        group['losses'],
                        avg_profit
                    )
                    
                    patterns.append({
                        'pattern_key': pattern_key,
                        'context_hash': context_hash,
                        'win_rate': win_rate,
                        'total_occurrences': total,
                        'average_profit': avg_profit,
                        'confidence': min(1.0, win_rate * (total / 10))
                    })
        
        # Sort by confidence
        patterns.sort(key=lambda x: x['confidence'], reverse=True)
        
        return patterns
    
    def predict_decision_quality(self, decision: Dict) -> Dict:
        """
        Predict if a decision is likely to be good or bad based on learned patterns
        
        Args:
            decision: Decision to evaluate
            
        Returns:
            Dictionary with prediction and confidence
        """
        features = self.extract_context_features(decision)
        context_hash = self.build_context_hash(features)
        
        learned_patterns = self.tracker.get_learned_patterns()
        
        # Find matching patterns
        matching_patterns = []
        for pattern in learned_patterns:
            if pattern['context_hash'] == context_hash:
                matching_patterns.append(pattern)
        
        if not matching_patterns:
            return {
                'prediction': 'UNKNOWN',
                'confidence': 0,
                'reason': 'No similar decisions in history'
            }
        
        # Use best matching pattern
        best_pattern = max(matching_patterns, key=lambda p: p['confidence'])
        win_rate = best_pattern['win_count'] / (best_pattern['win_count'] + best_pattern['loss_count'])
        
        if win_rate > 0.65:
            prediction = 'LIKELY_WIN'
        elif win_rate > 0.55:
            prediction = 'SLIGHT_EDGE'
        elif win_rate > 0.45:
            prediction = 'RISKY'
        else:
            prediction = 'LIKELY_LOSS'
        
        return {
            'prediction': prediction,
            'confidence': best_pattern['confidence'],
            'win_rate_from_history': win_rate,
            'pattern_occurrences': best_pattern['win_count'] + best_pattern['loss_count'],
            'reason': f"Based on {best_pattern['win_count']} wins and {best_pattern['loss_count']} losses"
        }
    
    def get_player_profile(self) -> Dict:
        """
        Build a complete profile of the player's betting style and performance
        
        Returns:
            Comprehensive player profile
        """
        stats = self.tracker.get_decision_stats()
        style = self.identify_player_style()
        patterns = self.learn_winning_patterns()
        performance = self.analyze_decision_patterns()
        
        return {
            'generated_at': datetime.now().isoformat(),
            'decision_statistics': stats,
            'player_style': style,
            'learned_patterns': patterns[:10],
            'performance_analysis': performance,
            'profile_summary': {
                'total_decisions': stats.get('total_decisions', 0),
                'overall_win_rate': stats.get('win_rate', 0),
                'total_profit': stats.get('total_profit', 0),
                'ai_alignment': style.get('ai_alignment', 'UNKNOWN'),
                'best_bet_target': performance.get('best_targets', [{}])[0].get('bet_target') if performance.get('best_targets') else None,
                'confidence_level': len(patterns) / 10  # Confidence in profile
            }
        }
    
    def compare_decision_quality(self, manual_decisions: List[Dict], 
                                ai_decisions: List[Dict]) -> Dict:
        """
        Compare quality of manual vs AI recommendations
        
        Args:
            manual_decisions: Manually made decisions
            ai_decisions: AI recommended decisions
            
        Returns:
            Comparison dictionary
        """
        def calc_metrics(decisions):
            if not decisions:
                return {'wins': 0, 'losses': 0, 'win_rate': 0, 'avg_profit': 0}
            
            wins = sum(1 for d in decisions if d['outcome'] == 'win')
            losses = sum(1 for d in decisions if d['outcome'] == 'loss')
            total = wins + losses
            profits = [d['profit_loss'] for d in decisions if d['profit_loss']]
            
            return {
                'wins': wins,
                'losses': losses,
                'win_rate': wins / total if total > 0 else 0,
                'avg_profit': statistics.mean(profits) if profits else 0,
                'total_profit': sum(profits)
            }
        
        manual_metrics = calc_metrics(manual_decisions)
        ai_metrics = calc_metrics(ai_decisions)
        
        # Determine which is better
        if ai_metrics['win_rate'] > manual_metrics['win_rate']:
            recommendation = "Follow AI more often"
        elif manual_metrics['win_rate'] > ai_metrics['win_rate']:
            recommendation = "Trust your intuition"
        else:
            recommendation = "Mix manual and AI decisions"
        
        return {
            'manual_performance': manual_metrics,
            'ai_performance': ai_metrics,
            'ai_advantage': ai_metrics['win_rate'] - manual_metrics['win_rate'],
            'recommendation': recommendation
        }
    
    def get_decision_improvement_tips(self) -> List[str]:
        """
        Provide tips for improving decision making based on analysis
        
        Returns:
            List of actionable improvement tips
        """
        tips = []
        profile = self.get_player_profile()
        performance = profile['performance_analysis']
        
        if performance.get('status') == 'insufficient_data':
            return ["Make more decisions to get personalized tips"]
        
        # Tip 1: Focus on best targets
        best_targets = performance.get('best_targets', [])
        if best_targets:
            tips.append(f"Your best bets are: {', '.join([t['bet_target'] for t in best_targets[:3]])} "
                       f"(avg {best_targets[0]['win_rate']:.0%} win rate)")
        
        # Tip 2: Avoid worst targets
        worst_targets = performance.get('worst_targets', [])
        if worst_targets and worst_targets[0]['win_rate'] < 0.4:
            tips.append(f"Avoid betting {worst_targets[0]['bet_target']} "
                       f"({worst_targets[0]['win_rate']:.0%} win rate)")
        
        # Tip 3: AI alignment
        style = profile['player_style']
        if style.get('ai_alignment') == 'TRUSTS_INTUITION':
            tips.append("Your intuition is strong! Keep making manual decisions")
        elif style.get('ai_alignment') == 'TRUSTS_AI':
            tips.append("You perform better with AI suggestions - consider relying on them more")
        
        # Tip 4: Betting amount
        all_decisions = self.tracker.get_decisions_by_source('manual', limit=100)
        amounts = [d['bet_amount'] for d in all_decisions]
        avg_amount = statistics.mean(amounts) if amounts else 0
        
        wins_by_amount = defaultdict(list)
        for d in all_decisions:
            tier = self._classify_amount(d['bet_amount'])
            if d['outcome'] == 'win':
                wins_by_amount[tier].append(d['profit_loss'] or 0)
        
        best_tier = max(wins_by_amount.items(), key=lambda x: statistics.mean(x[1])) if wins_by_amount else None
        if best_tier:
            tips.append(f"You perform best with {best_tier[0]} bets - adjust your bet sizing accordingly")
        
        return tips
    
    # ──────────────────────────────────────────────────────────────────
    # INVESTMENT LEARNING
    # ──────────────────────────────────────────────────────────────────
    
    def record_investment_outcome(self, investment_id: int, profit_loss: float, 
                                 capital: float, duration_minutes: int = 0,
                                 mesa_types: List[str] = None) -> None:
        """
        Record investment outcome for learning
        
        Args:
            investment_id: Investment ID
            profit_loss: Total profit/loss from investment
            capital: Initial capital invested
            duration_minutes: How long investment was active
            mesa_types: Types of tables used in this investment
        """
        if not hasattr(self.tracker, 'db_path'):
            return
        
        try:
            roi = (profit_loss / capital * 100) if capital > 0 else 0
            is_win = 1 if profit_loss >= 0 else 0
            
            conn = sqlite3.connect(self.tracker.db_path)
            cursor = conn.cursor()
            
            # Record in a learned_investments table
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS learned_investments "
                "(id INTEGER PRIMARY KEY, investment_id INTEGER, "
                " profit_loss REAL, capital REAL, roi REAL, is_win INTEGER, "
                " duration_minutes INTEGER, mesa_types TEXT, recorded_at TEXT)"
            )
            
            cursor.execute(
                "INSERT INTO learned_investments "
                "(investment_id, profit_loss, capital, roi, is_win, duration_minutes, mesa_types, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (investment_id, profit_loss, capital, roi, is_win, 
                 duration_minutes, json.dumps(mesa_types or []), 
                 datetime.now().isoformat())
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
    
    def analyze_investment_performance(self) -> Dict:
        """
        Analyze all investments to find winning patterns
        
        Returns:
            Investment performance statistics
        """
        try:
            if not hasattr(self.tracker, 'db_path'):
                return {'status': 'no_db_path'}
            
            conn = sqlite3.connect(self.tracker.db_path)
            cursor = conn.cursor()
            
            # Get all recorded investments
            cursor.execute(
                "SELECT investment_id, profit_loss, capital, roi, is_win, duration_minutes "
                "FROM learned_investments ORDER BY recorded_at DESC"
            )
            investments = cursor.fetchall()
            conn.close()
            
            if not investments:
                return {'status': 'no_data', 'total_investments': 0}
            
            # Analyze patterns
            wins = sum(1 for inv in investments if inv[4] == 1)
            total = len(investments)
            win_rate = (wins / total * 100) if total > 0 else 0
            
            # Calculate averages
            avg_roi = statistics.mean([inv[3] for inv in investments])
            avg_capital = statistics.mean([inv[2] for inv in investments])
            total_profit = sum(inv[1] for inv in investments)
            
            # Profit by capital size
            small_capital = [inv for inv in investments if inv[2] < avg_capital/2]
            large_capital = [inv for inv in investments if inv[2] > avg_capital*2]
            
            small_roi = statistics.mean([inv[3] for inv in small_capital]) if small_capital else 0
            large_roi = statistics.mean([inv[3] for inv in large_capital]) if large_capital else 0
            
            return {
                'status': 'success',
                'total_investments': total,
                'wins': wins,
                'win_rate': win_rate,
                'total_profit': total_profit,
                'avg_roi': avg_roi,
                'avg_capital': avg_capital,
                'small_capital_roi': small_roi,
                'large_capital_roi': large_roi,
                'best_investment': max(investments, key=lambda x: x[1]) if investments else None,
                'worst_investment': min(investments, key=lambda x: x[1]) if investments else None,
            }
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    def get_investment_recommendations(self) -> List[str]:
        """
        Get investment-level recommendations based on learning
        
        Returns:
            List of recommendations
        """
        analysis = self.analyze_investment_performance()
        recs = []
        
        if analysis.get('status') != 'success':
            return ["Insufficient investment history to analyze"]
        
        inv_count = analysis.get('total_investments', 0)
        if inv_count < 3:
            return [f"Create more investments to get better recommendations ({inv_count}/3)"]
        
        win_rate = analysis.get('win_rate', 0)
        avg_roi = analysis.get('avg_roi', 0)
        
        # Win rate recommendation
        if win_rate >= 60:
            recs.append(f"✅ Excellent! {win_rate:.0f}% of your investments are profitable")
        elif win_rate >= 50:
            recs.append(f"Good! {win_rate:.0f}% of your investments are profitable")
        else:
            recs.append(f"Focus on profitability - only {win_rate:.0f}% of investments profit")
        
        # ROI recommendation
        if avg_roi > 0:
            recs.append(f"📈 Average ROI: {avg_roi:.1f}% per investment")
        else:
            recs.append(f"⚠️  Average ROI is negative ({avg_roi:.1f}%) - review strategy")
        
        # Capital size recommendation
        small_roi = analysis.get('small_capital_roi', 0)
        large_roi = analysis.get('large_capital_roi', 0)
        
        if small_roi > large_roi and large_roi > 0:
            recs.append("💡 Try smaller investments for better returns")
        elif large_roi > small_roi and small_roi > 0:
            recs.append("💡 Consider increasing your investment size")
        
        return recs
