import os
import asyncio
import dotenv
from dotenv import load_dotenv

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client
from utils.utils import get_clients
from streamlit_pages import database, environment

# Ensure your environment variables are loaded
load_dotenv()

# Import the asynchronous function from your module
# Adjust the import below to match your project structure.
from archon.crawl_pydantic_ai_docs import get_title_and_summary
from archon.crawl_pydantic_ai_docs import crawl_parallel_with_requests

def get_supabase_client():
    """
    The goal of this was to ensure that supabase was initialized as expected.
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    if not supabase_url or not supabase_key:
        raise Exception("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in environment variables.")
    
    url = database.get_supabase_sql_editor_url(supabase_url)
    return create_client(supabase_url, supabase_key)

async def test_chunk_title_summary():
    """
    When using local LLMs, the title and summary was almost always an error.
    After testing, response_format was refactored and now works as expected.
    """
    # Get the Supabase client
    openai_client, supabase = get_clients()
    
    # Retrieve one record from the site_pages table
    response = supabase.table("site_pages").select("*").limit(1).execute()
    
    if not response.data:
        print("No records found in site_pages.")
        return

    # Extract chunk details
    record = response.data[0]
    content = record.get("content", "")
    url = record.get("url", "Unknown URL")

    print(f"Testing chunk from URL: {url}")
    
    # Use your local model to get title and summary from the chunk content
    result = await get_title_and_summary(content, url)
    
    print("\nTest Result:")
    print("Title:", result.get("title", "No title returned"))
    print("Summary:", result.get("summary", "No summary returned"))

def test_database_tab():
    openai_client, supabase = get_clients()

    database.database_tab(supabase)

async def test_reprocess_error_pages():
    """
    The orginal intent of this function was to add it to the crawl_pydantic_ai_docs.py
    but it has not been added.

    TODO: start a GitHub thread to discuss if this would be a welcomed feature
    """
    # Get the clients (adjust get_clients if necessary)
    openai_client, supabase = get_clients()

    # Query for records where title is "Error processing title"
    response = supabase.table("site_pages") \
        .select("*") \
        .eq("title", "Error processing title") \
        .execute()

    if not response.data:
        print("No records with title 'Error processing title' found.")
        return

    # Group records by URL and store the first encountered content for each URL
    error_pages = {}
    for record in response.data:
        url = record.get("url")
        if url and url not in error_pages:
            error_pages[url] = record.get("content", "")

    # Process each URL
    for url, content in error_pages.items():
        print(f"\nProcessing URL: {url}")
        
        # Reprocess the URL using the asynchronous function
        result = await get_title_and_summary(content, url)
        new_title = result.get("title", "")
        new_summary = result.get("summary", "")
        
        # Check if reprocessing was successful by ensuring the title has changed
        if new_title and new_title != "Error processing title":
            print(f"Reprocessing successful for URL {url}. New title: {new_title}")

            # Delete all records in the database with this URL
            del_response = supabase.table("site_pages").delete().eq("url", url).execute()
            print(f"Deleted records for URL: {url}")

            await crawl_parallel_with_requests([url])
            # Insert the newly processed record into the database
            #insert_data = {
            #    "url": url,
            #    "content": content,  # Update content if needed
            #    "title": new_title,
            #    "summary": new_summary
            #}
            #insert_response = supabase.table("site_pages").insert(insert_data).execute()
            #print(f"Inserted updated record for URL {url}: {insert_response.data}")
        else:
            print(f"Reprocessing failed for URL {url}. Keeping the existing error records.")


if __name__ == "__main__":
    """
    Uncomment and use the debugger to step through each of these examples
    to ensure functionality works as expected
    """
    asyncio.run(test_reprocess_error_pages())
    
    #get_supabase_client()
    
    # When using local LLMs, these tabs were not instantiating object properly. Since
    # there are no unit tests, this was the only way to step through with the debugger
    #test_database_tab()
    #environment.environment_tab()
    
    # asyncio.run(test_chunk_title_summary())
    
    
