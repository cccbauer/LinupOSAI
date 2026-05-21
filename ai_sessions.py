"""
AI Sessions Module - Session management and repository for Linup
Stores complete session history with metadata for pattern analysis
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
import os

@dataclass
class Bet:
    """Individual bet in a session"""
    bet_id: str  # e.g., '34', 'R', 'W1'
    amount: float
    type: str  # 'group' or 'number'
    result: Optional[str]  # 'win', 'loss', None if pending

@dataclass
class Spin:
    """Individual spin record"""
    spin_number: int
    result: int  # Winning number (0-36)
    bets: List[Bet]  # Bets placed on this spin
    timestamp: datetime

@dataclass
class Session:
    """Complete betting session"""
    session_id: str
    created_at: datetime
    spins: List[Spin]
    starting_capital: float
    ending_capital: float
    notes: str = ""
    groups_used: List[str] = None  # Groups that were bet on
    progression_mode: str = "manual"  # 'fibonacci', 'martingale', etc.

class SessionRepository:
    """Manages session storage and retrieval"""
    
    def __init__(self, db_path: str = "linup_sessions.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT,
                starting_capital REAL,
                ending_capital REAL,
                total_spins INTEGER,
                win_count INTEGER,
                loss_count INTEGER,
                roi REAL,
                notes TEXT,
                groups_used TEXT,
                progression_mode TEXT
            )
        ''')
        
        # Spins table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS spins (
                spin_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                spin_number INTEGER,
                result_number INTEGER,
                timestamp TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        ''')
        
        # Bets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bets (
                bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
                spin_id INTEGER,
                bet_name TEXT,
                amount REAL,
                bet_type TEXT,
                bet_result TEXT,
                FOREIGN KEY(spin_id) REFERENCES spins(spin_id)
            )
        ''')
        
        # Patterns table (detected patterns)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detected_patterns (
                pattern_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                pattern_type TEXT,
                pattern_data TEXT,
                confidence REAL,
                detected_at TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_session(self, session: Session) -> bool:
        """Save a complete session to repository"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Save session metadata
            roi = ((session.ending_capital - session.starting_capital) / 
                   session.starting_capital * 100) if session.starting_capital > 0 else 0
            
            cursor.execute('''
                INSERT OR REPLACE INTO sessions 
                (session_id, created_at, starting_capital, ending_capital, 
                 total_spins, roi, notes, groups_used, progression_mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session.session_id,
                session.created_at.isoformat(),
                session.starting_capital,
                session.ending_capital,
                len(session.spins),
                roi,
                session.notes,
                json.dumps(session.groups_used or []),
                session.progression_mode
            ))
            
            # Save spins and bets
            for spin in session.spins:
                cursor.execute('''
                    INSERT INTO spins (session_id, spin_number, result_number, timestamp)
                    VALUES (?, ?, ?, ?)
                ''', (
                    session.session_id,
                    spin.spin_number,
                    spin.result,
                    spin.timestamp.isoformat()
                ))
                
                spin_id = cursor.lastrowid
                
                # Save bets for this spin
                for bet in spin.bets:
                    cursor.execute('''
                        INSERT INTO bets (spin_id, bet_name, amount, bet_type, bet_result)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        spin_id,
                        bet.bet_id,
                        bet.amount,
                        bet.type,
                        bet.result
                    ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error saving session: {e}")
            return False
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve a complete session by ID"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get session metadata
            cursor.execute('SELECT * FROM sessions WHERE session_id = ?', (session_id,))
            session_row = cursor.fetchone()
            
            if not session_row:
                return None
            
            # Get spins
            cursor.execute('''
                SELECT * FROM spins WHERE session_id = ? ORDER BY spin_number
            ''', (session_id,))
            spin_rows = cursor.fetchall()
            
            spins = []
            for spin_row in spin_rows:
                # Get bets for this spin
                cursor.execute('SELECT * FROM bets WHERE spin_id = ?', (spin_row['spin_id'],))
                bet_rows = cursor.fetchall()
                
                bets = [
                    Bet(
                        bet_id=bet['bet_name'],
                        amount=bet['amount'],
                        type=bet['bet_type'],
                        result=bet['bet_result']
                    )
                    for bet in bet_rows
                ]
                
                spins.append(Spin(
                    spin_number=spin_row['spin_number'],
                    result=spin_row['result_number'],
                    bets=bets,
                    timestamp=datetime.fromisoformat(spin_row['timestamp'])
                ))
            
            conn.close()
            
            return Session(
                session_id=session_row['session_id'],
                created_at=datetime.fromisoformat(session_row['created_at']),
                spins=spins,
                starting_capital=session_row['starting_capital'],
                ending_capital=session_row['ending_capital'],
                notes=session_row['notes'],
                groups_used=json.loads(session_row['groups_used']),
                progression_mode=session_row['progression_mode']
            )
        except Exception as e:
            print(f"Error retrieving session: {e}")
            return None
    
    def get_all_sessions(self) -> List[Dict]:
        """Get list of all sessions with summary info"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT session_id, created_at, starting_capital, ending_capital, 
                       total_spins, roi, progression_mode
                FROM sessions ORDER BY created_at DESC
            ''')
            
            sessions = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return sessions
        except Exception as e:
            print(f"Error retrieving sessions: {e}")
            return []
    
    def get_sessions_by_date_range(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Get sessions within a date range"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT session_id, created_at, starting_capital, ending_capital, 
                       total_spins, roi, progression_mode
                FROM sessions 
                WHERE created_at BETWEEN ? AND ?
                ORDER BY created_at DESC
            ''', (start_date.isoformat(), end_date.isoformat()))
            
            sessions = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return sessions
        except Exception as e:
            print(f"Error retrieving sessions by date range: {e}")
            return []
    
    def save_detected_pattern(self, session_id: str, pattern_type: str, 
                            pattern_data: Dict, confidence: float):
        """Save a detected pattern to the database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO detected_patterns 
                (session_id, pattern_type, pattern_data, confidence, detected_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                session_id,
                pattern_type,
                json.dumps(pattern_data),
                confidence,
                datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error saving pattern: {e}")
            return False
    
    def get_patterns_by_type(self, pattern_type: str) -> List[Dict]:
        """Get all detected patterns of a specific type"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM detected_patterns 
                WHERE pattern_type = ?
                ORDER BY confidence DESC
            ''', (pattern_type,))
            
            patterns = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return patterns
        except Exception as e:
            print(f"Error retrieving patterns: {e}")
            return []
    
    def get_all_patterns(self) -> List[Dict]:
        """Get all detected patterns across all sessions"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM detected_patterns 
                ORDER BY confidence DESC
            ''')
            
            patterns = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return patterns
        except Exception as e:
            print(f"Error retrieving all patterns: {e}")
            return []
    
    def get_database_stats(self) -> Dict:
        """Get overall statistics about the session repository"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM sessions')
            total_sessions = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM spins')
            total_spins = cursor.fetchone()[0]
            
            cursor.execute('SELECT SUM(ending_capital - starting_capital) FROM sessions')
            total_profit = cursor.fetchone()[0] or 0
            
            cursor.execute('SELECT AVG(roi) FROM sessions')
            avg_roi = cursor.fetchone()[0] or 0
            
            cursor.execute('SELECT COUNT(*) FROM detected_patterns')
            total_patterns = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total_sessions': total_sessions,
                'total_spins': total_spins,
                'total_profit': total_profit,
                'average_roi': avg_roi,
                'total_patterns_detected': total_patterns
            }
        except Exception as e:
            print(f"Error getting database stats: {e}")
            return {}
