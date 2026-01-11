# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Overview

This is a Google Apps Script project that provides utilities for reading and manipulating Google Sheets data. The codebase is written in JavaScript for the Google Apps Script runtime environment.

## Architecture

### Core Components

**SheetRow** (`SheetDataReader.gs`)
- Represents a single row from a spreadsheet
- Provides header-based data access via `get(headerName)` method
- Stores data internally as a key-value object where keys are header names

**SheetDataReader** (`SheetDataReader.gs`)
- Main interface for reading spreadsheet data
- Takes spreadsheet URL, sheet name, and optional header row number (default: 1)
- Automatically loads all data on instantiation
- Provides methods: `getRows()`, `getRow(index)`, `filter(predicate)`, `forEach(callback)`, `getHeaders()`, `getRowCount()`
- Uses Google Apps Script's `SpreadsheetApp` API

### Design Pattern

The codebase follows an object-oriented approach where:
1. Data is loaded once during `SheetDataReader` construction
2. Row data is wrapped in `SheetRow` objects for convenient access
3. Header names are used as keys rather than column indices

## Development Commands

Since this is a Google Apps Script project, development happens in the online Apps Script editor. There are no local build, test, or lint commands.

### Deployment

Code must be deployed through the Google Apps Script web interface:
1. Copy the code to the Apps Script editor at script.google.com
2. Test using the `example()` function or create custom test functions
3. Use `Logger.log()` for debugging output (viewable in Execution log)

## Key Constraints

- Code runs in Google Apps Script runtime (similar to ES6 JavaScript but with GAS-specific APIs)
- Must use `SpreadsheetApp` API for spreadsheet operations
- No npm packages or external dependencies available
- All code must be in `.gs` files
- Class syntax is supported but some modern ES features may not be available
