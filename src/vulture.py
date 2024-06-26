import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import pandas as pd
import praw
import spacy

# Load the pre-trained NLP model
nlp = spacy.load("en_core_web_sm")

# Load environment variables from .env files
load_dotenv(os.path.join(os.path.dirname(__file__), '../vulture_cred.env'))
load_dotenv(os.path.join(os.path.dirname(__file__), '../src/vulture_lib.env'))

# Set up Reddit instance with credentials from environment variables
reddit = praw.Reddit(
    client_id=os.getenv('REDDIT_CLIENT_ID'),
    client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
    user_agent=os.getenv('REDDIT_USER_AGENT')
)

# Load known stock symbols from environment variable, vulture_lib.env
known_stock_symbols = os.getenv('KNOWN_STOCK_SYMBOLS').split(',')

# Function to fetch posts with pagination
def fetch_posts(subreddit_name, post_type='top', time_filter='day', limit=50):
    subreddit = reddit.subreddit(subreddit_name)
    posts = []
    last_post = None
    
    while len(posts) < limit:
        if post_type == 'top':
            new_posts = subreddit.top(time_filter=time_filter, limit=limit, params={'after': last_post})
        elif post_type == 'new':
            new_posts = subreddit.new(limit=limit, params={'after': last_post})
        
        new_posts = list(new_posts)
        if not new_posts:
            break

        last_post = new_posts[-1].name
        posts.extend(new_posts)
    
    return posts[:limit]

# Combined function to extract primary stock symbol from title and body
def extract_primary_stock_symbol(title, body):
    pattern_with_dollar = re.compile(r'\$[A-Za-z]{2,5}(?=\b|\))')
    pattern_without_dollar = re.compile(r'[A-Za-z]{2,5}(?=\b|\))')

    def extract_symbols(text):
        # Use regular expressions to find potential stock symbols
        symbols_with_dollar = pattern_with_dollar.findall(text)
        symbols_without_dollar = pattern_without_dollar.findall(text)

        # Remove $ from symbols_with_dollar and convert all symbols to uppercase
        symbols_with_dollar = [symbol[1:].upper() for symbol in symbols_with_dollar]
        symbols_without_dollar = [symbol.upper() for symbol in symbols_without_dollar]

        # Print found symbols for debugging
        # print(f"Symbols with dollar: {symbols_with_dollar}")
        # print(f"Symbols without dollar: {symbols_without_dollar}")

        # Combine and deduplicate symbols found by regex
        combined_symbols = list(set(symbols_with_dollar + symbols_without_dollar))

        # Extract entities using SpaCy
        doc = nlp(text)
        spacy_symbols = [ent.text.upper() for ent in doc.ents if ent.label_ == "ORG"]

        # for testing
        #print(f"Entities found by SpaCy: {spacy_symbols}")

        # Combine all symbols
        all_symbols = list(set(combined_symbols + spacy_symbols))
        # print (f'All found symbols {all_symbols}')

        # Count occurrences of each symbol
        symbol_counts = Counter(all_symbols)
        # print(f"Symbol counts: {symbol_counts}")

        # Sort symbols by their counts in descending order
        sorted_symbols = sorted(symbol_counts.items(), key=lambda x: x[1], reverse=True)
        # print(f"Sorted symbols by frequency: {sorted_symbols}")

        # Filter symbols against known stock symbols
        found_symbol = [symbol for symbol, count in sorted_symbols if symbol in known_stock_symbols]
        # print(f"Filtered valid symbols: {found_symbol}")

        return found_symbol

    title_symbols = extract_symbols(title)
    if title_symbols:
        return title_symbols[0]

    body_symbols = extract_symbols(body)
    if body_symbols:
        return body_symbols[0]

    return None


# Function to extract position/investment details
def extract_investment_details(text):
    # Remove line breaks
    text = text.replace('\n', ' ')
    
    # Define patterns to match the position headers
    position_patterns = [
        r'positions:',
        r'my position:',
        r'my positions:',
        r'positions -'
    ]

    # Define patterns to match the price range targeting
    price_range_pattern = re.compile(r'targeting a price range of \$?(\d+\.?\d*)\s*-\s*\$?(\d+\.?\d*)', re.IGNORECASE)
    
    # Define pattern to match position details
    detail_pattern = re.compile(
        r'(\$?\d+\.?\d*)\s*(Call|Put|Calls|Puts)\s*(Expiry\s*\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}/\d{1,2}|\w+\s*\d{1,2}(?:st|nd|rd|th)?|\d{1,2}(?:st|nd|rd|th)?\s*\w+|\d{1,2}(?:st|nd|rd|th)?\s*\w+\s*\d{4})',
        re.IGNORECASE
    )
    
    # Combine patterns into a single regex pattern
    combined_pattern = r'|'.join(position_patterns)
    
    # Check for position headers
    position_header_match = re.search(combined_pattern, text, re.IGNORECASE)
    positions = []
    if position_header_match:
        # Text after the position header
        positions_text = text[position_header_match.end():]
        
        # Check for position details in the text
        matches = detail_pattern.findall(positions_text)
        for match in matches:
            full_statement = ' '.join(match).strip()
            positions.append(full_statement)
        
        # Check for price range targeting details in the text
        price_range_matches = price_range_pattern.findall(positions_text)
        for match in price_range_matches:
            full_statement = f'Targeting a price range of ${match[0]} - ${match[1]}'
            positions.append(full_statement)
    
    # Return the positions as a list
    return positions



# Function to get OP's account karma
def get_account_karma(author):
    try:
        user = reddit.redditor(author)
        return user.link_karma + user.comment_karma
    except Exception as e:
        print(f"Error fetching karma for user {author}: {e}")
        return None

# Function to process posts and extract details
# Function to process posts and extract details
def process_posts(posts):
    data = []
    current_time = datetime.now(timezone.utc)
    
    for post in posts:
        post_time = datetime.fromtimestamp(post.created_utc, timezone.utc)
        # Ignore posts older than 1 day
        if post_time < current_time - timedelta(days=1):  
            continue
        # Ignore posts with image/video links
        if post.url.endswith('.jpeg') or post.url.endswith('.png') or 'https://v.redd.it/' in post.url or not post.url.startswith('https://www.reddit.com'):
            continue
        
        symbol = extract_primary_stock_symbol(post.title, post.selftext)
        investment_details = extract_investment_details(post.selftext)
        karma = get_account_karma(post.author.name)
        
        data.append({
            'Title': post.title,
            'Stock Symbol': symbol,
            'Position': ', '.join(investment_details),  # Join multiple positions with a comma
            'OP Karma': karma,
            'URL': post.url
        })
    return data

# Main function to fetch and save posts from multiple subreddits to an Excel file
def main():
    subreddits = ['options', 'wallstreetbets', 'shortsqueeze']
    post_types = ['top', 'new']

    top_posts_data = []
    new_posts_data = []

    for subreddit in subreddits:
        for post_type in post_types:
            print(f'Fetching {post_type} posts from r/{subreddit}...')
            posts = fetch_posts(subreddit, post_type=post_type, limit=50)
            if post_type == 'top':
                top_posts_data.extend(process_posts(posts))
            elif post_type == 'new':
                new_posts_data.extend(process_posts(posts))

    top_posts_df = pd.DataFrame(top_posts_data)
    new_posts_df = pd.DataFrame(new_posts_data)

    # Save to Excel in the data directory
    data_dir = os.path.join(os.path.dirname(__file__), '../data')
    os.makedirs(data_dir, exist_ok=True)
    excel_path = os.path.join(data_dir, 'reddit_posts.xlsx')

    with pd.ExcelWriter(excel_path) as writer:
        top_posts_df.to_excel(writer, sheet_name='Top Posts', index=False)
        new_posts_df.to_excel(writer, sheet_name='New Posts', index=False)

    print(f'Data saved to {excel_path}')

if __name__ == "__main__":
    main()
