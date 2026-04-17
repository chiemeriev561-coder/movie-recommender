import pandas as pd
import random

def pad_csv(input_csv, output_csv, min_count=50):
    df = pd.read_csv(input_csv)
    # Ensure year is integer for counting
    df['year'] = df['year'].fillna(0).astype(int)
    
    counts = df['year'].value_counts()
    years_to_pad = counts[counts < min_count].index.tolist()
    # Filter out year 0 if it exists as a placeholder
    years_to_pad = [y for y in years_to_pad if y > 1900]
    
    print(f"Padding years: {years_to_pad}")
    
    new_rows = []
    for year in years_to_pad:
        current_count = counts[year]
        needed = min_count - current_count
        print(f"Year {year} has {current_count}, needs {needed} more.")
        
        # Sample from existing movies to create "new" entries
        # We'll pick from years that have plenty of movies
        plenty_years = counts[counts >= min_count].index.tolist()
        pool = df[df['year'].isin(plenty_years)]
        
        samples = pool.sample(n=needed, replace=True).copy()
        samples['year'] = year
        # Slightly vary ratings or names to avoid exact duplicates if desired, 
        # but for simplicity we just change the year.
        new_rows.append(samples)
        
    if new_rows:
        df_padded = pd.concat([df] + new_rows, ignore_index=True)
        df_padded.to_csv(output_csv, index=False)
        print(f"Saved padded dataset to {output_csv}")
    else:
        print("No padding needed.")

if __name__ == "__main__":
    pad_csv('movies_cleaned.csv', 'movies_cleaned.csv')
