"""
AI Decision Tracker - Records all player decisions for learning
Tracks what bets you made, your reasoning, and outcomes
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from enum import Enum

class DecisionOutcome(Enum):
    """Enum for decision outcomes"""
    WIN = "win"
    LOSS = "loss"
    BREAK_EVEN = "break_even"
    PENDING = "pending"

@dataclass
class Decision:
    """Represents a single betting decision"""
    decision_id: str
    session_id: str
    spin_number: int
    
    # What was decided
    bet_target: str  # e.g., '34', 'R', '14'
    bet_type: str  # 'group' or 'number'
    bet_amount: float
    
    # Why it was decided
    decision_context: Dict  # Contains: confidence, reason, patterns_detected, etc.
    source: str  # 'manual', 'ai_recommendation', 'learned_pattern', etc.
    
    # When it was decided
    decision_time: datetime
    
    # What happened
    spin_result: Optional[int]  # The winning number
    outcome: str  # 'win', 'loss', 'break_even', 'pending'
    profit_loss: Optional[float]  # Actual P&L from this decision
    
    # Feedback
    player_satisfaction: Optional[int] = None  # 1-5 rating (1=bad, 5=great)
    notes: str = ""

class DecisionTracker:
    """Tracks all player decisions for learning and analysis"""
    
    def __init__(self, db_path: str = "linup_sessions.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize decision tracking tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Decisions table - tracks every decision made
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS decisions (
                decision_id TEXT PRIMARY KEY,
                session_id TEXT,
                spin_number INTEGER,
                bet_target TEXT,
                bet_type TEXT,
                bet_amount REAL,
                decision_context TEXT,
                source TEXT,
                decision_time TEXT,
                spin_result INTEGER,
                outcome TEXT,
                profit_loss REAL,
                player_satisfaction INTEGER,
                notes TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        ''')
        
        # Decision feedback - for user's explicit feedback
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS decision_feedback (
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id TEXT,
                rating INTEGER,
                comment TEXT,
                feedback_time TEXT,
                FOREIGN KEY(decision_id) REFERENCES decisions(decision_id)
            )
        ''')
        
        # Decision patterns - learned recurring patterns
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS learned_patterns (
                pattern_id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_pattern_key TEXT,
                context_hash TEXT,
                decision_feature_set TEXT,
                win_count INTEGER,
                loss_count INTEGER,
                average_profit REAL,
                confidence REAL,
                last_used TEXT,
                created_at TEXT,
                UNIQUE(context_hash)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def record_decision(self, decision: Decision) -> bool:
        """Record a player decision"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO decisions
                (decision_id, session_id, spin_number, bet_target, bet_type, 
                 bet_amount, decision_context, source, decision_time, 
                 spin_result, outcome, profit_loss, player_satisfaction, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                decision.decision_id,
                decision.session_id,
                decision.spin_number,
                decision.bet_target,
                decision.bet_type,
                decision.bet_amount,
                json.dumps(decision.decision_context),
                decision.source,
                decision.decision_time.isoformat(),
                decision.spin_result,
                decision.outcome,
                decision.profit_loss,
                decision.player_satisfaction,
                decision.notes
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error recording decision: {e}")
            return False
    
    def record_outcome(self, decision_id: str, spin_result: int, 
                      outcome: str, profit_loss: float) -> bool:
        """Update decision with outcome after spin result is known"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE decisions 
                SET spin_result = ?, outcome = ?, profit_loss = ?
                WHERE decision_id = ?
            ''', (spin_result, outcome, profit_loss, decision_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error recording outcome: {e}")
            return False
    
    def add_feedback(self, decision_id: str, rating: int, comment: str = "") -> bool:
        """Add player feedback to a decision (1-5 rating)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO decision_feedback 
                (decision_id, rating, comment, feedback_time)
                VALUES (?, ?, ?, ?)
            ''', (decision_id, rating, comment, datetime.now().isoformat()))
            
            # Also update the decision's satisfaction
            cursor.execute('''
                UPDATE decisions 
                SET player_satisfaction = ?
                WHERE decision_id = ?
            ''', (rating, decision_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error adding feedback: {e}")
            return False
    
    def get_decision(self, decision_id: str) -> Optional[Dict]:
        """Retrieve a specific decision"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM decisions WHERE decision_id = ?', (decision_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                decision = dict(row)
                decision['decision_context'] = json.loads(decision['decision_context'])
                return decision
            return None
        except Exception as e:
            print(f"Error retrieving decision: {e}")
            return None
    
    def get_decisions_by_session(self, session_id: str) -> List[Dict]:
        """Get all decisions from a session"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM decisions 
                WHERE session_id = ?
                ORDER BY spin_number ASC
            ''', (session_id,))
            
            rows = cursor.fetchall()
            conn.close()
            
            decisions = []
            for row in rows:
                decision = dict(row)
                decision['decision_context'] = json.loads(decision['decision_context'])
                decisions.append(decision)
            
            return decisions
        except Exception as e:
            print(f"Error retrieving session decisions: {e}")
            return []
    
    def get_decisions_by_target(self, bet_target: str, limit: int = 100) -> List[Dict]:
        """Get all decisions for a specific bet target (e.g., group '34', number '14')"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM decisions 
                WHERE bet_target = ?
                ORDER BY decision_time DESC
                LIMIT ?
            ''', (bet_target, limit))
            
            rows = cursor.fetchall()
            conn.close()
            
            decisions = []
            for row in rows:
                decision = dict(row)
                decision['decision_context'] = json.loads(decision['decision_context'])
                decisions.append(decision)
            
            return decisions
        except Exception as e:
            print(f"Error retrieving decisions by target: {e}")
            return []
    
    def get_decisions_by_source(self, source: str, limit: int = 100) -> List[Dict]:
        """Get decisions filtered by source (e.g., 'ai_recommendation', 'manual')"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM decisions 
                WHERE source = ?
                ORDER BY decision_time DESC
                LIMIT ?
            ''', (source, limit))
            
            rows = cursor.fetchall()
            conn.close()
            
            decisions = []
            for row in rows:
                decision = dict(row)
                decision['decision_context'] = json.loads(decision['decision_context'])
                decisions.append(decision)
            
            return decisions
        except Exception as e:
            print(f"Error retrieving decisions by source: {e}")
            return []
    
    def get_decision_stats(self) -> Dict:
        """Get statistics about all decisions"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Total decisions
            cursor.execute('SELECT COUNT(*) FROM decisions')
            total_decisions = cursor.fetchone()[0]
            
            # Wins/losses
            cursor.execute("SELECT COUNT(*) FROM decisions WHERE outcome = 'win'")
            wins = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM decisions WHERE outcome = 'loss'")
            losses = cursor.fetchone()[0]
            
            # Total profit
            cursor.execute("SELECT SUM(profit_loss) FROM decisions WHERE outcome IN ('win', 'loss')")
            total_profit = cursor.fetchone()[0] or 0
            
            # Average profit per decision
            cursor.execute("SELECT AVG(profit_loss) FROM decisions WHERE outcome IN ('win', 'loss')")
            avg_profit = cursor.fetchone()[0] or 0
            
            # Win rate
            win_rate = (wins / total_decisions) if total_decisions > 0 else 0
            
            # Decision sources
            cursor.execute('''
                SELECT source, COUNT(*) as count 
                FROM decisions 
                GROUP BY source
            ''')
            source_counts = dict(cursor.fetchall())
            
            conn.close()
            
            return {
                'total_decisions': total_decisions,
                'wins': wins,
                'losses': losses,
                'win_rate': win_rate,
                'total_profit': total_profit,
                'average_profit_per_decision': avg_profit,
                'decision_sources': source_counts
            }
        except Exception as e:
            print(f"Error getting decision stats: {e}")
            return {}
    
    def get_decisions_with_outcomes(self) -> List[Dict]:
        """Get all decisions that have outcomes (not pending)"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM decisions
                WHERE outcome IN ('win', 'loss', 'break_even')
                ORDER BY decision_time DESC
            ''')
            
            rows = cursor.fetchall()
            conn.close()
            
            decisions = []
            for row in rows:
                decision = dict(row)
                decision['decision_context'] = json.loads(decision['decision_context'])
                decisions.append(decision)
            
            return decisions
        except Exception as e:
            print(f"Error retrieving decisions with outcomes: {e}")
            return []
    
    def get_decisions_with_feedback(self) -> List[Dict]:
        """Get decisions that have player feedback"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT d.*, df.rating, df.comment 
                FROM decisions d
                LEFT JOIN decision_feedback df ON d.decision_id = df.feedback_id
                WHERE d.player_satisfaction IS NOT NULL
                ORDER BY d.decision_time DESC
            ''')
            
            rows = cursor.fetchall()
            conn.close()
            
            decisions = []
            for row in rows:
                decision = dict(row)
                decision['decision_context'] = json.loads(decision['decision_context'])
                decisions.append(decision)
            
            return decisions
        except Exception as e:
            print(f"Error retrieving decisions with feedback: {e}")
            return []
    
    def save_learned_pattern(self, pattern_key: str, context_hash: str, 
                            feature_set: Dict, win_count: int, loss_count: int, 
                            average_profit: float) -> bool:
        """Save a learned pattern to the database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Calculate confidence based on win rate
            total = win_count + loss_count
            if total > 0:
                win_rate = win_count / total
                # Confidence is higher with more data and higher win rate
                confidence = (win_rate * (1 + (total / 100)))  # Cap around 2.0
                confidence = min(confidence, 1.0)
            else:
                confidence = 0
            
            cursor.execute('''
                INSERT OR REPLACE INTO learned_patterns
                (player_pattern_key, context_hash, decision_feature_set, 
                 win_count, loss_count, average_profit, confidence, last_used, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                pattern_key,
                context_hash,
                json.dumps(feature_set),
                win_count,
                loss_count,
                average_profit,
                confidence,
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error saving learned pattern: {e}")
            return False
    
    def get_learned_patterns(self) -> List[Dict]:
        """Get all learned patterns"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM learned_patterns
                ORDER BY confidence DESC
            ''')
            
            rows = cursor.fetchall()
            conn.close()
            
            patterns = []
            for row in rows:
                pattern = dict(row)
                pattern['decision_feature_set'] = json.loads(pattern['decision_feature_set'])
                patterns.append(pattern)
            
            return patterns
        except Exception as e:
            print(f"Error retrieving learned patterns: {e}")
            return []
