try:
    import isort

    print("isort available")
    code = "import logging\nimport sys\n"
    print("Original:")
    print(code)
    print("Sorted:")
    print(isort.code(code, profile="black", line_length=100))
except ImportError:
    print("isort not installed")
