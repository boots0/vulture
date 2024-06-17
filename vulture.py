import os
import praw
import re
import pandas as pd
from collections import Counter
from dotenv import load_dotenv

# Load environment variables from .env files
load_dotenv('vulture_cred.env')
load_dotenv('vulture_lib.env')

# Set up Reddit instance with credentials from environment variables
reddit = praw.Reddit(
    client_id=os.getenv('REDDIT_CLIENT_ID'),
    client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
    user_agent=os.getenv('REDDIT_USER_AGENT')
)

# Load known stock symbols from environment variable
known_stock_symbols = os.getenv('KNOWN_STOCK_SYMBOLS').split(',')

# Function to fetch posts
def fetch_posts(subreddit_name, post_type='top', time_filter='day', limit=10):
    subreddit = reddit.subreddit(subreddit_name)
    posts = []
    
    if post_type == 'top':
        for post in subreddit.top(time_filter=time_filter, limit=limit):
            posts.append(post)
    elif post_type == 'new':
        for post in subreddit.new(limit=limit):
            posts.append(post)
    
    return posts

# Combined function to extract primary stock symbol from title and body
def extract_primary_stock_symbol(title, body):
    def extract_stock_symbols(text):
        # Using regex, search for strings that are 1-5 capitalized letters, w/ or w/o $
        pattern_with_dollar = re.compile(r'\$[A-Z]{1,5}')
        pattern_without_dollar = re.compile(r'\b[A-Z]{1,5}\b')

        symbols_with_dollar = pattern_with_dollar.findall(text)
        symbols_without_dollar = pattern_without_dollar.findall(text)

        # Remove the dollar sign for comparison with known symbols in known_stock_symbols
        symbols_with_dollar = [symbol[1:] for symbol in symbols_with_dollar]

        # Validate symbols against known list
        valid_symbols_with_dollar = [symbol for symbol in symbols_with_dollar if symbol in known_stock_symbols]
        valid_symbols_without_dollar = [symbol for symbol in symbols_without_dollar if symbol in known_stock_symbols]

        return valid_symbols_with_dollar + valid_symbols_without_dollar

    # Check title first
    title_symbols = extract_stock_symbols(title)
    if title_symbols:
        return title_symbols[0]  # Return the first valid symbol found in the title

    # If no symbol found in title, check body and return the most common symbol
    body_symbols = extract_stock_symbols(body)
    if body_symbols:
        return Counter(body_symbols).most_common(1)[0][0]  # Return the most common symbol in the body

    return None  # Return None if no valid symbols found

# Function to extract position/investment details
def extract_investment_details(text):
    details = {}

    # Extract type of investment (put, call)
    investment_type_pattern = re.compile(r'\b(puts?|calls?|debit spread|credit spread|straddle|strangle)\b', re.IGNORECASE)
    investment_types = investment_type_pattern.findall(text)
    details['Investment Types'] = investment_types
    
    # Extract price range
    price_range_pattern = re.compile(r'\b(\d{1,5})(?:-\d{1,5})?\b')
    price_ranges = price_range_pattern.findall(text)
    details['Price Ranges'] = price_ranges
    
    # Extract specific investment actions like "200 $20c for 6/7 and 200 $20c for 9/20"
    action_pattern = re.compile(r'(\d+)\s*\$?(\d+)([pc])\s*for\s*(\d{1,2}/\d{1,2}(?:/\d{2,4})?)', re.IGNORECASE)
    actions = action_pattern.findall(text)
    details['Actions'] = [
        {
            'Contracts': contracts,
            'Strike Price': f"${strike}",
            'Type': 'Put' if type_ == 'p' else 'Call',
            'Expiration': expiration
        } for contracts, strike, type_, expiration in actions
    ]

    return details

# Function to get OP's account karma
# This helps validate the user's credibility
def get_account_karma(author):
    try:
        user = reddit.redditor(author)
        return user.link_karma + user.comment_karma
    except Exception as e:
        print(f"Error fetching karma for user {author}: {e}")
        return None

# Function to process posts and extract details
def process_posts(posts):
    data = []
    for post in posts:
        # Ignore image and video posts
        if post.url.endswith('.jpeg') or post.url.endswith('.png') or 'https://v.redd.it/' in post.url:
            continue
        
        symbol = extract_primary_stock_symbol(post.title, post.selftext)
        investment_details = extract_investment_details(post.selftext)
        karma = get_account_karma(post.author.name)
        
        data.append({
            'Title': post.title,
            'Stock Symbol': symbol,
            'Investment Types': ', '.join(investment_details['Investment Types']),
            'Price Ranges': ', '.join(investment_details['Price Ranges']),
            'Actions': '; '.join([f"{action['Contracts']} {action['Strike Price']} {action['Type']} for {action['Expiration']}" for action in investment_details['Actions']]),
            'OP Karma': karma,
            'URL': post.url
        })
    return data

# Main function to fetch and save posts from multiple subreddits to an Excel file
def main():
    subreddits = ['wallstreetbets', 'shortsqueeze', 'options']  # List of subreddits to scan
    post_types = ['top', 'new']  # Types of posts to fetch

    # DataFrames to store data
    top_posts_data = []
    new_posts_data = []

    for subreddit in subreddits:
        for post_type in post_types:
            print(f'Fetching {post_type} posts from r/{subreddit}...')
            posts = fetch_posts(subreddit, post_type=post_type, limit=10)
            if post_type == 'top':
                top_posts_data.extend(process_posts(posts))
            elif post_type == 'new':
                new_posts_data.extend(process_posts(posts))

    # Create DataFrames
    top_posts_df = pd.DataFrame(top_posts_data)
    new_posts_df = pd.DataFrame(new_posts_data)

    # Save to Excel
    with pd.ExcelWriter('reddit_posts.xlsx') as writer:
        top_posts_df.to_excel(writer, sheet_name='Top Posts', index=False)
        new_posts_df.to_excel(writer, sheet_name='New Posts', index=False)

    print('Data saved to reddit_posts.xlsx')

if __name__ == "__main__":
    main()
