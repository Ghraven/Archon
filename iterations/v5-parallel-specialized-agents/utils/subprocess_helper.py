import psutil
import shlex # To help parse command strings
import os    # To help normalize paths if needed (e.g., using os.path.basename)
import subprocess # To run external commands
import sys # To access stdout/stderr
import utils
import re


def extract_port(command_string):
  """
  Extracts the filename and port placeholder from a streamlit command string.

  Args:
    command_string: The command string to parse.

  Returns:
    A tuple containing the filename and port placeholder (filename, port),
    or (None, None) if the pattern is not found.
  """
  # Regex to find the filename after "streamlit run" and the value after "--server.port"
  match = re.search(r"\s+--server\.port\s+(\S+)", command_string)
  if match:
    port = match.group(1)
    return port
  else:
    return None


def is_thought_process_running():
    """
    Checks if a specific Streamlit thought_process command is running by examining process command lines.

    Returns:
        list[int]: A list of PIDs for matching running processes. Returns an empty list
                   if no matching process is found.
    """
    script_name="thought_stream_v3.py"
    matching_pids = []
    # These are the specific arguments we expect to find, in *addition* to 'streamlit' and 'run'
    required_args = {
        script_name,
        "run",
        "streamlit"
    }

    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            pinfo = proc.info
            cmdline = pinfo['cmdline']
            if not cmdline or len(cmdline) < 5 or "streamlit" not in set(cmdline):
                continue
            cmdline_set = set(os.path.basename(cmd) for cmd in cmdline)
            if cmdline_set and required_args.issubset(cmdline_set):
                print(cmdline)
                matching_pids.append(pinfo['pid'])
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        except Exception as e:
            print(f"[subprocess_helper] Error checking process {pinfo.get('pid', '?')}: {e}", file=sys.stderr)
            pass

    if(len(matching_pids) > 1):
        print(f"[subprocess_helper] though stream process running on multiple ports with PIDs: [{",".join(matching_pids)}]. Please kill the duplicate processes!")
            
    return len(matching_pids) > 0


def run_command(command_string: str):
    """
    Runs a command string in a subprocess.

    Args:
        command_string (str): The command to execute (e.g., "ls -l", "streamlit run app.py").

    Returns:
        bool: True if the command executed successfully (return code 0), False otherwise.
    """
    print(f"[subprocess_helper] Preparing to run command: {command_string}")
    try:
        # Use shlex.split to handle arguments properly and avoid shell injection issues
        args = shlex.split(command_string)
        print(f"[subprocess_helper] Executing args: {args}")

        # Run the command.
        # stdout and stderr are inherited from the parent process by default,
        # so the command's output will appear on the console.
        # check=False means it won't raise an exception on non-zero exit codes.
        # We capture the result to check the return code manually.
        result = subprocess.run(args, check=False, text=True) # Add text=True for better compatibility across platforms if needed

        # Log the outcome
        if result.returncode == 0:
            print(f"[subprocess_helper] Command finished successfully.")
            return True
        else:
            print(f"[subprocess_helper] Command failed with return code: {result.returncode}", file=sys.stderr)
            return False

    except FileNotFoundError:
        # This happens if the command itself (e.g., 'streamlit', 'ls') isn't found in the system PATH
        print(f"[subprocess_helper] Error: Command not found: '{args[0]}'. Make sure it's installed and in your PATH.", file=sys.stderr)
        return False
    except Exception as e:
        # Catch other potential exceptions during shlex.split or subprocess.run
        print(f"[subprocess_helper An error occurred while trying to run command: {e}", file=sys.stderr)
        return False

# --- Example Usage ---
if __name__ == "__main__":

    target_port = extract_port(get_tp_command())
    # Define the specifics of the command you are looking for
    target_script = "thought_stream_v3.py"
    # target_port = "8082"
    target_headless = "True" # psutil usually sees command line arguments as strings

    print(target_port)

    found_pids = is_thought_process_running()

    if found_pids:
        print(f"Found the Streamlit process running '{target_script}' on port {target_port}.")
        print(f"Matching PID(s): {found_pids}")
    else:
        print(f"The specific Streamlit process for '{target_script}' on port {target_port} was not found.")
