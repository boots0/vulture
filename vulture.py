import os
import praw
import re
import pandas as pd
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv('vulture_lib.env')

# Set up Reddit instance with credentials from environment variables
reddit = praw.Reddit(
    client_id=os.getenv('REDDIT_CLIENT_ID'),
    client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
    user_agent=os.getenv('REDDIT_USER_AGENT')
)


# List of known stock symbols (this can be expanded)
known_stock_symbols = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "FB", "NVDA", "NFLX", "BABA", "V", "JPM", "JNJ", "WMT",
    "PG", "DIS", "MA", "UNH", "HD", "PYPL", "BAC", "VZ", "ADBE", "CMCSA", "PFE", "KO", "NKE", "INTC",
    "MRK", "T", "CSCO", "PEP", "ABT", "CVX", "AVGO", "XOM", "QCOM", "MDT", "LLY", "CRM", "ACN", "COST",
    "TXN", "WFC", "DHR", "HON", "BMY", "MCD", "C", "AMGN", "NEE", "PM", "IBM", "UNP", "UPS", "LOW", "SCHW",
    "LIN", "ORCL", "AMD", "SPGI", "MS", "PLD", "GS", "BLK", "TMO", "INTU", "ISRG", "CAT", "ZTS", "NOW",
    "GE", "AMT", "AMAT", "LMT", "DE", "BKNG", "CVS", "SYK", "ADP", "CI", "MO", "MDLZ", "GILD", "MMM",
    "USB", "DUK", "FIS", "PNC", "AXP", "TJX", "TGT", "CB", "MMC", "ADI", "MET", "CME", "ADSK", "ANTM",
    "HUM", "COP", "ICE", "AON", "SO", "GM","GME", "FDX", "CCI", "APD", "BSX", "CSX", "EQIX", "WM", "TMUS",
    "BDX", "ITW", "NSC", "VRTX", "PGR", "EW", "NOC", "TRV", "SBUX", "CL", "CTAS", "MNST", "ETN", "KLAC",
    "EMR", "MCO", "ATVI", "ROST", "DLR", "PSA", "HCA", "KMB", "SHW", "LRCX", "MCHP", "EXC", "IDXX", "D",
    "TEL", "AEP", "SPG", "APH", "MAR", "MRNA", "PPG", "NXPI", "PH", "PSX", "ROK", "SRE", "AFL", "FTNT",
    "STZ", "TT", "ILMN", "CTSH", "HPQ", "ZBH", "PAYX", "ECL", "KMI", "PRU", "BK", "DG", "ED", "GIS",
    "WMB", "JCI", "ORLY", "HAL", "KHC", "MNST", "VLO", "HIG", "ES", "MPC", "YUM", "ODFL", "DFS", "MCK",
    "WBA", "TDG", "DLTR", "A", "GPN", "FISV", "MSI", "MSCI", "SNPS", "CERN", "SWK", "AVB", "HSY", "CINF",
    "VFC", "CNC", "MLM", "AWK", "DHI", "MTB", "VTR", "XEL", "PPL", "LEN", "PEG", "RSG", "LUV", "WST",
    "NRG", "WEC", "ARE", "SBAC", "WAT", "CBRE", "HPE", "TSN", "WELL", "EXPD", "EXR", "MAA", "AMP", "EQR",
    "ESS", "PPG", "ETR", "BXP", "DTE", "NEE", "FE", "EVRG", "CMS", "ATO", "AES", "LNT", "PNW", "IDA",
    "SJI", "SR", "AVA", "ALE", "MGEE", "NWE", "OGE", "OTTR", "POR", "WRB", "AJG", "WLTW", "AIG", "TRV",
    "ALL", "PGR", "MET", "HIG", "CNA", "SIGI", "CINF", "CB", "AON", "MMC", "EIG", "KMPR", "WRB", "CNO",
    "RLI", "Y", "HCC", "JRVR", "RNR", "ARGO", "NODK", "NWLI", "THG", "MKL", "AFG", "SIGI", "SAFT", "MCY"
]

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

# Function to extract stock symbols from text
def extract_stock_symbols(text):
    pattern_with_dollar = re.compile(r'\$[A-Z]{1,5}')
    pattern_without_dollar = re.compile(r'\b[A-Z]{1,5}\b')
    
    symbols_with_dollar = pattern_with_dollar.findall(text)
    symbols_without_dollar = pattern_without_dollar.findall(text)
    
    # Remove the dollar sign for comparison with known symbols
    symbols_with_dollar = [symbol[1:] for symbol in symbols_with_dollar]
    
    # Validate symbols against known list
    valid_symbols_with_dollar = [symbol for symbol in symbols_with_dollar if symbol in known_stock_symbols]
    valid_symbols_without_dollar = [symbol for symbol in symbols_without_dollar if symbol in known_stock_symbols]
    
    return set(valid_symbols_with_dollar + valid_symbols_without_dollar)

# Function to extract position/investment details
def extract_investment_details(text):
    # A basic pattern to find investment details, like "bought 100 shares at $150"
    pattern = re.compile(r'\b(buy|bought|sell|sold)\b.*?\b\d+\s*shares?\b.*?\b\d+\.?\d*\b')
    matches = pattern.findall(text)
    return matches

# Function to get OP's account karma
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
        if post.url.endswith('.jpeg') or post.url.endswith('.png') or 'https://v.redd.it/' in post.url:
            continue
        
        symbols = extract_stock_symbols(post.selftext)
        investment_details = extract_investment_details(post.selftext)
        karma = get_account_karma(post.author.name)
        
        data.append({
            'Title': post.title,
            'Stock Symbols': ', '.join(symbols),
            'Investment Details': ', '.join(investment_details),
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
