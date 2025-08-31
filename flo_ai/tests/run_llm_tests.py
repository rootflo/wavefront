#!/usr/bin/env python3
"""
Test runner script for all LLM tests in the Flo AI framework.
This script runs comprehensive tests for all LLM implementations.
"""

import sys
import os
import subprocess
import time

# Add the flo_ai directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def run_tests_for_llm(test_file, llm_name):
    """Run tests for a specific LLM implementation."""
    print(f"\n{'='*60}")
    print(f'🧪 Running tests for {llm_name}')
    print(f"{'='*60}")

    start_time = time.time()

    try:
        # Run pytest for the specific test file
        result = subprocess.run(
            [
                sys.executable,
                '-m',
                'pytest',
                test_file,
                '-v',  # Verbose output
                '--tb=short',  # Short traceback format
                '--color=yes',  # Colored output
            ],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(__file__),
        )

        end_time = time.time()
        duration = end_time - start_time

        if result.returncode == 0:
            print(f'✅ {llm_name} tests PASSED in {duration:.2f}s')
            print('📊 Output:')
            print(result.stdout)
        else:
            print(f'❌ {llm_name} tests FAILED in {duration:.2f}s')
            print('📊 Output:')
            print(result.stdout)
            print('🚨 Errors:')
            print(result.stderr)

        return result.returncode == 0, duration

    except Exception as e:
        print(f'💥 Error running {llm_name} tests: {e}')
        return False, 0


def run_all_llm_tests():
    """Run all LLM tests and provide a summary."""
    print('🚀 Starting comprehensive LLM test suite for Flo AI')
    print(f'📁 Test directory: {os.path.dirname(__file__)}')
    print(f'🐍 Python executable: {sys.executable}')

    # Define all LLM test files
    test_files = [
        ('test_base_llm.py', 'BaseLLM & ImageMessage'),
        ('test_openai_llm.py', 'OpenAI LLM'),
        ('test_anthropic_llm.py', 'Anthropic Claude LLM'),
        ('test_gemini_llm.py', 'Google Gemini LLM'),
        ('test_ollama_llm.py', 'Ollama LLM'),
        ('test_vertexai_llm.py', 'Google VertexAI LLM'),
        ('test_openai_vllm.py', 'OpenAI VLLM'),
    ]

    results = []
    total_tests = 0
    passed_tests = 0
    total_duration = 0

    for test_file, llm_name in test_files:
        test_path = os.path.join(os.path.dirname(__file__), test_file)

        if not os.path.exists(test_path):
            print(f'⚠️  Test file not found: {test_file}')
            continue

        success, duration = run_tests_for_llm(test_path, llm_name)
        results.append((llm_name, success, duration))

        if success:
            passed_tests += 1
        total_tests += 1
        total_duration += duration

    # Print summary
    print(f"\n{'='*60}")
    print('📋 TEST SUMMARY')
    print(f"{'='*60}")

    for llm_name, success, duration in results:
        status = '✅ PASSED' if success else '❌ FAILED'
        print(f'{llm_name:<25} {status:<10} {duration:>8.2f}s')

    print('\n📊 Overall Results:')
    print(f'   Total LLM implementations: {total_tests}')
    print(f'   Passed: {passed_tests}')
    print(f'   Failed: {total_tests - passed_tests}')
    print(f'   Success rate: {(passed_tests/total_tests)*100:.1f}%')
    print(f'   Total test time: {total_duration:.2f}s')

    if passed_tests == total_tests:
        print('\n🎉 All LLM tests passed successfully!')
        return 0
    else:
        print('\n⚠️  Some LLM tests failed. Please check the output above.')
        return 1


def run_specific_llm_test(llm_name):
    """Run tests for a specific LLM implementation."""
    test_mapping = {
        'base': 'test_base_llm.py',
        'openai': 'test_openai_llm.py',
        'anthropic': 'test_anthropic_llm.py',
        'gemini': 'test_gemini_llm.py',
        'ollama': 'test_ollama_llm.py',
        'vertexai': 'test_vertexai_llm.py',
        'vllm': 'test_openai_vllm.py',
    }

    if llm_name.lower() not in test_mapping:
        print(f'❌ Unknown LLM: {llm_name}')
        print(f"Available options: {', '.join(test_mapping.keys())}")
        return 1

    test_file = test_mapping[llm_name.lower()]
    test_path = os.path.join(os.path.dirname(__file__), test_file)

    if not os.path.exists(test_path):
        print(f'❌ Test file not found: {test_file}')
        return 1

    success, duration = run_tests_for_llm(test_path, test_mapping[llm_name.lower()])
    return 0 if success else 1


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        # Run specific LLM test
        llm_name = sys.argv[1]
        return run_specific_llm_test(llm_name)
    else:
        # Run all LLM tests
        return run_all_llm_tests()


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
