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
def fetch_posts(subreddit_name, post_type='top', time_filter='day', limit=100):
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

# Combined function to extract primary stock symbol from title
def extract_primary_stock_symbol(title):
    pattern_with_dollar = re.compile(r'\$[A-Za-z]{2,5}(?=\b|\))')
    pattern_without_dollar = re.compile(r'[A-Za-z]{2,5}(?=\b|\))')

    # High ambiguity stock symbols (common words)
    ambiguous_symbols = {"CAN", "OR", "AND", "BUT", "AT", "ON", "CSP", "DTE", "FOR", "DD"}

    def extract_symbols(text):
        # Use regular expressions to find potential stock symbols
        symbols_with_dollar = pattern_with_dollar.findall(text)
        if symbols_with_dollar:
            # If any symbol is found with $, return it immediately
            return [symbol[1:].upper() for symbol in symbols_with_dollar]

        symbols_without_dollar = pattern_without_dollar.findall(text)

        # Extract entities using SpaCy and identify potential stock symbols
        doc = nlp(text)
        spacy_symbols = [
            ent.text.upper() for ent in doc.ents
            if ent.label_ == "ORG" and ent.text.upper() in known_stock_symbols
        ]

        # Combine all symbols
        all_symbols = list(set(symbols_without_dollar + spacy_symbols))

        # Use SpaCy to analyze the part of speech to deprioritize ambiguous symbols
        filtered_symbols = []
        for symbol in all_symbols:
            if symbol in ambiguous_symbols:
                # Check POS tagging for ambiguous symbols
                for token in doc:
                    if token.text.upper() == symbol and token.pos_ in {"VERB", "CCONJ", "ADP"}:
                        break
                else:
                    filtered_symbols.append(symbol)
            elif symbol in known_stock_symbols:
                filtered_symbols.append(symbol)

        return filtered_symbols

    # Extract and prioritize symbols from the title
    title_symbols = extract_symbols(title)
    if title_symbols:
        return title_symbols[0]

    return None


# Function to extract position/investment details
def extract_investment_details(text):
    # Step 1: Remove line breaks
    text = text.replace('\n', ' ')

    # Step 2: Split the text into sentences
    sentences = re.split(r'(?<=[.!?]) +', text)

    # Define a pattern to detect investment details more flexibly
    # The pattern matches a dollar amount, an option type (call/put), and an optional expiration date
    investment_pattern = re.compile(
        r'\$(\d+(\.\d{1,2})?)\s*(call|put|calls|puts)\s*((\d{1,2}/\d{1,2})(/\d{2,4})?)',
        re.IGNORECASE
    )

    # List to store identified positions
    positions = []

    # Step 3: Process each sentence individually
    for sentence in sentences:
        # Check for investment details in each sentence using the flexible pattern
        matches = investment_pattern.findall(sentence)
        for match in matches:
            dollar_amount = f'${match[0]}'
            option_type = match[2].capitalize()  # Capitalize the option type (e.g., Call or Put)
            expiration_date = match[3]  # Includes the full date match

            # Combine extracted details into a full statement
            full_statement = f'{dollar_amount} {option_type} {expiration_date}'.strip()
            positions.append(full_statement)

    # Step 4: Return the positions as a list
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
        # Ignore posts with image/video links
        if post.url.endswith('.jpeg') or post.url.endswith('.png') or 'https://v.redd.it/' in post.url or not post.url.startswith('https://www.reddit.com'):
            continue
        
        symbol = extract_primary_stock_symbol(post.title)
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
    post_types = ['top', 'new']  # We'll still use these to fetch the different types of posts

    # Create a dictionary to store combined data for each subreddit
    subreddit_data = {}

    for subreddit in subreddits:
        combined_posts = []
        
        # Fetch and process posts for each type (top and new)
        for post_type in post_types:
            print(f'Fetching {post_type} posts from r/{subreddit}...')
            posts = fetch_posts(subreddit, post_type=post_type, limit=100)
            combined_posts.extend(process_posts(posts))

        # Store combined data for each subreddit
        subreddit_data[subreddit] = combined_posts

    # Save to Excel in the data directory
    data_dir = os.path.join(os.path.dirname(__file__), '../data')
    os.makedirs(data_dir, exist_ok=True)
    excel_path = os.path.join(data_dir, 'reddit_posts_by_subreddit.xlsx')

    with pd.ExcelWriter(excel_path) as writer:
        for subreddit, posts_data in subreddit_data.items():
            # Create a DataFrame for each subreddit
            subreddit_df = pd.DataFrame(posts_data)
            subreddit_df.to_excel(writer, sheet_name=subreddit.capitalize(), index=False)

    print(f'Data saved to {excel_path}')

if __name__ == "__main__":
    main()
