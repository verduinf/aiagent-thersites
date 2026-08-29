import os
import sys
import ast
import re

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def find_python_files(src_dir):
    py_files = []
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith('.py'):
                py_files.append(os.path.join(root, f))
    return py_files

def audit_codebase(src_dir):
    print("=" * 80)
    print("ATHENA FULL CODEBASE AUDIT — UNUSED BRANCHES & DEAD CODE ANALYZER")
    print("=" * 80)
    
    py_files = find_python_files(src_dir)
    all_defined_funcs = {}
    all_called_funcs = set()
    
    for fpath in py_files:
        rel_path = os.path.relpath(fpath, src_dir)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            tree = ast.parse(content, filename=fpath)
            
            # Find function definitions
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    all_defined_funcs[node.name] = (rel_path, node.lineno)
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        all_called_funcs.add(node.func.id)
                    elif isinstance(node.func, ast.Attribute):
                        all_called_funcs.add(node.func.attr)
                        
        except Exception as e:
            print(f"Error parsing {rel_path}: {e}")

    print("\n🔍 AST PARSE & FUNCTION USAGE AUDIT:")
    print("-" * 70)
    unused_funcs = []
    for func_name, (rel_path, lineno) in sorted(all_defined_funcs.items()):
        # Ignore dunder methods, main dispatchers, and GUI handlers
        if func_name.startswith('__') or func_name in ['main', 'run_test_suite', 'run']:
            continue
        if func_name not in all_called_funcs:
            unused_funcs.append((func_name, rel_path, lineno))
            print(f"  ⚠️ Potential Unused Function: '{func_name}' in {rel_path}:{lineno}")

    if not unused_funcs:
        print("  ✅ Zero unused root functions detected!")

    print("\n" + "=" * 80)
    print(f"ATHENA AUDIT COMPLETE: Evaluated {len(py_files)} files across {src_dir}")
    print("=" * 80)

if __name__ == "__main__":
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    src_directory = os.path.join(project_root, "src")
    audit_codebase(src_directory)
