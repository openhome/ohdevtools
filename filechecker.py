from xml.etree.ElementTree import parse
from antglob import ant_glob
from collections import defaultdict


# Define a bunch of useful rules that can be applied to files in
# the source tree.

MSBUILD = "{http://schemas.microsoft.com/developer/msbuild/2003}"

def check_warnings_as_errors(filename):
    xmlroot = parse(filename)
    warning_elements = xmlroot.findall('.//'+MSBUILD+'TreatWarningsAsErrors')
    return len(warning_elements) >= 1 and all(x.text == 'true' for x in warning_elements)

def check_imports_prime(required_import, filename):
    xmlroot = parse(filename)
    import_elements = xmlroot.findall('.//'+MSBUILD+'Import')
    return any(x.attrib.get('Project', None) == required_import for x in import_elements)

def check_imports(required_import):
    def check_imports_partial(filename):
        return check_imports_prime(required_import, filename)
    return check_imports_partial

def check_notabs(filename):
    with open(filename,"r") as f:
        return not any('\t' in line for line in f)

def disallow(filename):
    return False

DEFAULT_DEFINITIONS = {
    'warnings-as-errors' : check_warnings_as_errors,
    'import-shared-settings' : check_imports('..\\SharedSettings.targets'),
    'no-tabs' : check_notabs,
    'disallow' : disallow
    }

def _print(message):
    print message

def apply_rules(rules, definitions = DEFAULT_DEFINITIONS, message_func=None):
    if message_func is None:
        message_func = _print
    files_to_check = defaultdict(set)
    for patterns, categories in rules:
        if not isinstance(patterns, list):
            patterns = [patterns]
        if not isinstance(categories, list):
            categories = [categories]
        for p in patterns:
            for filename in ant_glob(p):
                file_categories = files_to_check[filename]
                for category in categories:
                    if category.startswith('-'):
                        file_categories.discard(category[1:])
                    else:
                        file_categories.add(category)
    failures = defaultdict(set)
    for filename in sorted(files_to_check.keys()):
        for category in files_to_check[filename]:
            if not definitions[category](filename):
                failures[category].add(filename)
    message_func("{0} errors in {1} scanned files:".format(len(failures), len(files_to_check)))
    for category, filenames in sorted(failures.items()):
        if len(filenames) == 0:
            continue
        message_func("{0}, {1} files failed:".format(category, len(filenames)))
        for fname in sorted(filenames):
            print "    {0}".format(fname)
    return len(failures) == 0


