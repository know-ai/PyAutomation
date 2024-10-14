# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information
import os
import sys
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'PyAutomation'))
sys.path.insert(0, base_dir)

project = 'Pyautomation'
copyright = '2024, Intelcon System'
author = 'Intelcon System'
release = '0.1'




# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration



extensions = [
    'myst_parser',
    'sphinx.ext.autodoc',         
    'sphinx_rtd_theme',
    'sphinx.ext.napoleon',
    'sphinx.ext.graphviz'
]

templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
html_static_path = ['_static']
# html_css_files = [
#     'styles.css',  # Nombre del archivo que guardaste en _static
# ]
