# Grant Finder Project Commands & Guidelines

## Commands
- **Run crawler**: `python main.py` (with options: `--no-email`, `--no-google`, `--no-rss`)
- **Run with options**: `python main.py --max-depth 3 --concurrent 10 --delay 1.0`
- **Run tests**: `pytest` (once test files are added)
- **Run single test**: `pytest tests/test_file.py::test_function_name -v`

## Code Style
- **Imports**: Group in order: stdlib, third-party, local; use absolute imports
- **Types**: Use typing module annotations for all function parameters and returns
- **Naming**: snake_case for functions/variables, CamelCase for classes
- **Error handling**: Use try/except blocks with specific exceptions
- **Logging**: Use the configured logger (not print statements)
- **Documentation**: Docstrings for modules, classes, and functions (triple quotes)
- **Formatting**: Maintain 4-space indentation; line length <= 100 chars
- **Models**: Use Pydantic for data validation and serialization

## Structure
- Use async/await for network operations
- Separate concerns (crawling, parsing, reporting)
- Centralize configuration in src/config.py