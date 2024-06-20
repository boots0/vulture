import pandas as pd

# Function to convert a one-column spreadsheet to a comma-separated list
def spreadsheet_to_comma_list(file_path):
    # Load the spreadsheet
    data = pd.read_csv(file_path)
    
    # Get all values in the first column
    first_column_values = data.iloc[:, 0].tolist()
    
    # Convert to comma-separated list
    comma_separated_list = ", ".join(map(str, first_column_values))
    
    return comma_separated_list

# Example usage
file_path = '/Users/kalin/Documents/Projects/Vulture/nasdaq-listed.csv'  # Replace with your file path
comma_list = spreadsheet_to_comma_list(file_path)
print(comma_list)
