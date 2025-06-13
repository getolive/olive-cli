from olive.doctor import doctor_check
from olive.prompt_ui import olive_management_command

@olive_management_command('doctor')
def doctor_command(args: str = ""):
    """Run the Olive diagnostics and health check suite (:doctor)."""
    exit_code = doctor_check()
    if exit_code == 0:
        return  # all good, already printed
    else:
        # Print a final status and exit code if in failure
        print(f"Doctor finished with exit code {exit_code}")
        # Optionally: sys.exit(exit_code) if this is run from CLI
