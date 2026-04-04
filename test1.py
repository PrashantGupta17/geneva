from core.registry import ProviderRegistry

r = ProviderRegistry()
r.add_cli_provider('fake_cli', '/path/to/nowhere', 'fake_command --version')
success = r.verify_provider('fake_cli')
print(f"Verification Success: {success}")
if not success:
    print("Test passed: Wizard correctly identified failed CLI provider.")
else:
    print("Test failed!")
