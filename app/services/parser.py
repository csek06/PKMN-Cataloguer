import re
from dataclasses import dataclass
from typing import List, Set, Optional


@dataclass
class ParsedQuery:
    """Parsed search query components."""
    name_tokens: List[str]
    number: Optional[str]
    flags: Set[str]
    hints: List[str]


class QueryParser:
    """Parse natural language Pokémon card queries."""
    
    # Regex patterns
    NUMBER_PATTERN = re.compile(r'(?P<num>\d{1,3})(?:/(?P<of>\d{1,3}))?(?!\w)')  # Made /total optional
    STANDALONE_NUMBER_PATTERN = re.compile(r'\b(?P<num>\d{1,3})\b')  # For standalone numbers
    FLAGS_PATTERN = re.compile(
        r'\b(?:gx|ex|vmax|v[- ]?star|v\b|full\s*art|reverse|holo|shadowless)\b',
        re.IGNORECASE
    )
    
    # Set hints that might appear in queries
    SET_HINTS = {
        'base', 'jungle', 'fossil', 'rocket', 'gym', 'neo', 'discovery',
        'destiny', 'revelation', 'genesis', 'expedition', 'aquapolis',
        'skyridge', 'ruby', 'sapphire', 'emerald', 'diamond', 'pearl',
        'platinum', 'heartgold', 'soulsilver', 'black', 'white', 'xy',
        'sun', 'moon', 'sword', 'shield', 'brilliant', 'legends',
        'scarlet', 'violet', 'sv', 'sm', 'xy', 'bw', 'dp', 'ex', 'e',
        '151', '25th', 'anniversary', 'celebrations', 'evolutions',
        'generations', 'shining', 'hidden', 'fates', 'crimson', 'invasion',
        'astral', 'radiance', 'lost', 'origin', 'silver', 'tempest',
        'paradigm', 'trigger', 'crown', 'zenith', 'paldea', 'evolved'
    }
    
    @classmethod
    def parse(cls, query: str) -> ParsedQuery:
        """Parse a search query into components."""
        query = query.strip().lower()
        
        # Extract number (try full pattern first, then standalone)
        number = None
        number_match = cls.NUMBER_PATTERN.search(query)
        if number_match:
            number = number_match.group('num')
            # Remove the number pattern from query for further processing
            query = cls.NUMBER_PATTERN.sub('', query).strip()
        
        # Extract flags
        flags = set()
        flag_matches = cls.FLAGS_PATTERN.findall(query)
        for flag in flag_matches:
            # Normalize flag
            flag = flag.lower().replace(' ', '').replace('-', '')
            if flag == 'v':
                flags.add('v')
            elif 'vstar' in flag:
                flags.add('vstar')
            elif 'fullart' in flag:
                flags.add('fullart')
            else:
                flags.add(flag)
        
        # Remove flags from query
        query = cls.FLAGS_PATTERN.sub('', query).strip()
        
        # Extract set hints and handle standalone numbers
        hints = []
        query_words = query.split()
        
        # Process each word
        for word in query_words[:]:  # Copy list to modify during iteration
            if word in cls.SET_HINTS:
                # If this is a non-numeric set hint, always treat as hint
                if not word.isdigit():
                    hints.append(word)
                    query_words.remove(word)
                # For numeric set hints, the logic depends on context
                elif word.isdigit():
                    if number is None:
                        # If we have flags (like "ex", "gx"), treat numeric words as card numbers
                        # Otherwise, treat as set hints
                        if flags:
                            number = word
                            query_words.remove(word)
                        else:
                            hints.append(word)
                            query_words.remove(word)
                    else:
                        # We already have a number, so this is definitely a hint
                        hints.append(word)
                        query_words.remove(word)
            elif word.isdigit() and number is None and flags:
                # If we have flags and no number yet, treat standalone digits as card numbers
                # This handles cases like "buzzwole gx 57"
                standalone_match = cls.STANDALONE_NUMBER_PATTERN.match(word)
                if standalone_match:
                    number = word
                    query_words.remove(word)
        
        # Remaining words are name tokens
        name_tokens = [word for word in query_words if word.strip()]
        
        return ParsedQuery(
            name_tokens=name_tokens,
            number=number,
            flags=flags,
            hints=hints
        )
