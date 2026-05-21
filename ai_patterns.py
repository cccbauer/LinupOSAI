"""
AI Patterns Module - Pattern detection algorithms for Linup
Detects recurring patterns in betting sequences and outcomes
"""

from typing import List, Dict, Set, Tuple, Optional
from collections import Counter, deque
import statistics
from datetime import datetime

class PatternDetector:
    """Detects patterns in roulette spins and betting sequences"""
    
    def __init__(self, grupos_maestros: Dict[str, Set[int]], wheel_neighbors: Dict[int, Set[int]]):
        """
        Initialize with group definitions and wheel neighbors
        
        Args:
            grupos_maestros: Dictionary of group definitions
            wheel_neighbors: Dictionary mapping numbers to their wheel neighbors
        """
        self.grupos = grupos_maestros
        self.wheel_neighbors = wheel_neighbors
    
    def detect_number_frequency_patterns(self, spin_results: List[int], 
                                        window_size: int = 20) -> Dict:
        """
        Detect frequently occurring numbers in recent spins
        
        Args:
            spin_results: List of winning numbers in order
            window_size: Number of recent spins to analyze
            
        Returns:
            Dictionary with hot/cold numbers and confidence scores
        """
        if len(spin_results) < window_size:
            window = spin_results
        else:
            window = spin_results[-window_size:]
        
        counter = Counter(window)
        total = len(window)
        
        # Calculate frequency percentages
        frequencies = {num: count / total for num, count in counter.items()}
        
        # Hot numbers (appeared more than 1/37 of the time)
        expected_frequency = 1 / 37
        hot_numbers = {num: freq for num, freq in frequencies.items() 
                      if freq > expected_frequency * 1.5}
        cold_numbers = {num: freq for num, freq in frequencies.items() 
                       if freq < expected_frequency * 0.5}
        
        return {
            'pattern_type': 'number_frequency',
            'hot_numbers': hot_numbers,
            'cold_numbers': cold_numbers,
            'window_size': len(window),
            'analysis_date': datetime.now().isoformat()
        }
    
    def detect_group_clustering(self, spin_results: List[int], 
                               window_size: int = 25) -> List[Dict]:
        """
        Detect which groups are clustering together
        
        Args:
            spin_results: List of winning numbers
            window_size: Number of recent spins to analyze
            
        Returns:
            List of group patterns with clustering scores
        """
        if len(spin_results) < window_size:
            window = spin_results
        else:
            window = spin_results[-window_size:]
        
        patterns = []
        
        # Check each group's hit rate in the window
        group_hits = {}
        for group_name, group_numbers in self.grupos.items():
            hits = sum(1 for num in window if num in group_numbers)
            hit_rate = hits / len(window)
            expected_rate = len(group_numbers) / 37
            
            # Only report groups with significant deviation
            deviation = hit_rate - expected_rate
            if abs(deviation) > expected_rate * 0.3:  # 30% deviation threshold
                group_hits[group_name] = {
                    'hits': hits,
                    'hit_rate': hit_rate,
                    'expected_rate': expected_rate,
                    'deviation': deviation,
                    'confidence': min(1.0, abs(deviation) / expected_rate)
                }
        
        # Sort by confidence
        for group_name in sorted(group_hits.keys(), 
                                key=lambda g: group_hits[g]['confidence'], 
                                reverse=True):
            patterns.append({
                'pattern_type': 'group_clustering',
                'group': group_name,
                **group_hits[group_name]
            })
        
        return patterns
    
    def detect_neighbor_clustering(self, spin_results: List[int], 
                                  window_size: int = 20) -> Dict:
        """
        Detect if neighboring numbers on the wheel are appearing together
        
        Args:
            spin_results: List of winning numbers
            window_size: Number of recent spins to analyze
            
        Returns:
            Dictionary with neighbor clustering information
        """
        if len(spin_results) < window_size:
            window = spin_results
        else:
            window = spin_results[-window_size:]
        
        # Count how often consecutive spins have neighbors on the wheel
        neighbor_hits = 0
        consecutive_pairs = 0
        
        for i in range(len(window) - 1):
            current = window[i]
            next_num = window[i + 1]
            consecutive_pairs += 1
            
            if next_num in self.wheel_neighbors.get(current, set()):
                neighbor_hits += 1
        
        if consecutive_pairs == 0:
            neighbor_rate = 0
        else:
            neighbor_rate = neighbor_hits / consecutive_pairs
        
        # Expected rate of neighbors is ~2/37 (two neighbors out of 37 numbers)
        expected_neighbor_rate = 2 / 37
        
        return {
            'pattern_type': 'neighbor_clustering',
            'neighbor_hits': neighbor_hits,
            'total_pairs': consecutive_pairs,
            'neighbor_rate': neighbor_rate,
            'expected_rate': expected_neighbor_rate,
            'deviation': neighbor_rate - expected_neighbor_rate,
            'confidence': min(1.0, abs(neighbor_rate - expected_neighbor_rate) / expected_neighbor_rate) 
                        if expected_neighbor_rate > 0 else 0,
            'window_size': len(window)
        }
    
    def detect_repeating_sequences(self, spin_results: List[int], 
                                  seq_length: int = 3) -> List[Dict]:
        """
        Detect repeating sequences of numbers
        
        Args:
            spin_results: List of winning numbers
            seq_length: Length of sequences to detect
            
        Returns:
            List of repeating sequence patterns
        """
        if len(spin_results) < seq_length * 2:
            return []
        
        sequences = Counter()
        
        # Extract all sequences of given length
        for i in range(len(spin_results) - seq_length + 1):
            seq = tuple(spin_results[i:i + seq_length])
            sequences[seq] += 1
        
        # Find sequences that repeat (appear more than once)
        repeating = []
        for seq, count in sequences.items():
            if count > 1:
                repeating.append({
                    'pattern_type': 'repeating_sequence',
                    'sequence': list(seq),
                    'occurrences': count,
                    'confidence': min(1.0, count / len(spin_results)),
                    'length': seq_length
                })
        
        # Sort by confidence
        repeating.sort(key=lambda x: x['confidence'], reverse=True)
        
        return repeating[:10]  # Return top 10 patterns
    
    def detect_color_patterns(self, spin_results: List[int], 
                            rojos: Set[int], window_size: int = 20) -> Dict:
        """
        Detect patterns in red/black sequences
        
        Args:
            spin_results: List of winning numbers
            rojos: Set of red numbers
            window_size: Number of recent spins to analyze
            
        Returns:
            Dictionary with color pattern information
        """
        if len(spin_results) < window_size:
            window = spin_results
        else:
            window = spin_results[-window_size:]
        
        color_sequence = ['R' if num in rojos else 'B' for num in window]
        
        # Count runs of same color
        runs = []
        current_color = color_sequence[0]
        current_run = 1
        
        for i in range(1, len(color_sequence)):
            if color_sequence[i] == current_color:
                current_run += 1
            else:
                runs.append((current_color, current_run))
                current_color = color_sequence[i]
                current_run = 1
        runs.append((current_color, current_run))
        
        # Analyze run lengths
        run_lengths = Counter([run[1] for run in runs])
        max_run = max(run_lengths.keys()) if run_lengths else 0
        
        # Count color distribution
        red_count = sum(1 for num in window if num in rojos)
        black_count = len(window) - red_count
        red_pct = red_count / len(window)
        black_pct = black_count / len(window)
        
        return {
            'pattern_type': 'color_pattern',
            'red_percentage': red_pct,
            'black_percentage': black_pct,
            'max_run_length': max_run,
            'run_distribution': dict(run_lengths),
            'color_sequence': ''.join(color_sequence),
            'window_size': len(window)
        }
    
    def detect_odd_even_patterns(self, spin_results: List[int], 
                               window_size: int = 20) -> Dict:
        """
        Detect patterns in odd/even sequences
        
        Args:
            spin_results: List of winning numbers
            window_size: Number of recent spins to analyze
            
        Returns:
            Dictionary with odd/even pattern information
        """
        if len(spin_results) < window_size:
            window = spin_results
        else:
            window = spin_results[-window_size:]
        
        oe_sequence = ['O' if num % 2 == 1 else 'E' for num in window]
        
        # Count runs
        runs = []
        current_parity = oe_sequence[0]
        current_run = 1
        
        for i in range(1, len(oe_sequence)):
            if oe_sequence[i] == current_parity:
                current_run += 1
            else:
                runs.append((current_parity, current_run))
                current_parity = oe_sequence[i]
                current_run = 1
        runs.append((current_parity, current_run))
        
        # Analyze
        run_lengths = Counter([run[1] for run in runs])
        odd_count = sum(1 for num in window if num % 2 == 1)
        even_count = len(window) - odd_count
        
        return {
            'pattern_type': 'odd_even_pattern',
            'odd_percentage': odd_count / len(window),
            'even_percentage': even_count / len(window),
            'max_run_length': max(run_lengths.keys()) if run_lengths else 0,
            'run_distribution': dict(run_lengths),
            'oe_sequence': ''.join(oe_sequence),
            'window_size': len(window)
        }
    
    def detect_dozen_patterns(self, spin_results: List[int], 
                            window_size: int = 25) -> List[Dict]:
        """
        Detect patterns across the three dozens (1-12, 13-24, 25-36)
        
        Args:
            spin_results: List of winning numbers
            window_size: Number of recent spins to analyze
            
        Returns:
            List of dozen patterns
        """
        if len(spin_results) < window_size:
            window = spin_results
        else:
            window = spin_results[-window_size:]
        
        dozens = {
            '1-12': set(range(1, 13)),
            '13-24': set(range(13, 25)),
            '25-36': set(range(25, 37)),
            '0': {0}
        }
        
        patterns = []
        for dozen_name, dozen_set in dozens.items():
            hits = sum(1 for num in window if num in dozen_set)
            hit_rate = hits / len(window)
            expected_rate = len(dozen_set) / 37
            
            patterns.append({
                'pattern_type': 'dozen_pattern',
                'dozen': dozen_name,
                'hits': hits,
                'hit_rate': hit_rate,
                'expected_rate': expected_rate,
                'deviation': hit_rate - expected_rate,
                'confidence': min(1.0, abs(hit_rate - expected_rate) / expected_rate) 
                            if expected_rate > 0 else 0
            })
        
        return sorted(patterns, key=lambda x: x['confidence'], reverse=True)
    
    def analyze_all_patterns(self, spin_results: List[int], 
                           rojos: Set[int]) -> Dict[str, any]:
        """
        Run comprehensive pattern analysis on spin results
        
        Args:
            spin_results: List of all winning numbers
            rojos: Set of red numbers
            
        Returns:
            Dictionary with all detected patterns
        """
        results = {
            'analysis_time': datetime.now().isoformat(),
            'total_spins': len(spin_results),
            'patterns': {}
        }
        
        if len(spin_results) > 0:
            results['patterns']['number_frequency'] = self.detect_number_frequency_patterns(spin_results)
            results['patterns']['group_clustering'] = self.detect_group_clustering(spin_results)
            results['patterns']['neighbor_clustering'] = self.detect_neighbor_clustering(spin_results)
            results['patterns']['repeating_sequences'] = self.detect_repeating_sequences(spin_results)
            results['patterns']['color_patterns'] = self.detect_color_patterns(spin_results, rojos)
            results['patterns']['odd_even_patterns'] = self.detect_odd_even_patterns(spin_results)
            results['patterns']['dozen_patterns'] = self.detect_dozen_patterns(spin_results)
        
        return results
