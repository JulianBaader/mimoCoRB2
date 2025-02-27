import os
import sys

sys.path.insert(0, os.path.abspath("../../"))


# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'mimoCoRB2'
copyright = '2025, Julian Baader'
author = 'Julian Baader'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
    'sphinx_autodoc_typehints',
    'sphinx.ext.duration',
    'sphinx.ext.doctest',
]

# sphinx-autodoc-typehints settings
always_use_bars_union = True
typehints_defaults = 'braces'

napoleon_use_rtype = True
typehints_use_rtype = True
typehints_document_rtype = True

#typehints_use_signature = True
#typehints_use_signature_return = True


templates_path = ['_templates']
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'alabaster'
html_static_path = ['_static']
