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

**ProductInfoFetcher** (`ProductInfoFetcher.gs`)
- Fetches product information from ASIN using Keepa API and Amazon SP-API
- Returns: product name, image URL, release date, size, weight, sales commission, FBA fee
- Combines data from both APIs for comprehensive product information
- Handles API errors gracefully with fallback logic

**KeepaClient** (`ProductInfoFetcher.gs`)
- Wrapper for Keepa API
- Fetches product data including title, images, dimensions, weight, and release date
- Converts Keepa time format to ISO date format

**SpApiClient** (`ProductInfoFetcher.gs`)
- Wrapper for Amazon Selling Partner API (SP-API)
- Handles OAuth token refresh automatically
- Fetches catalog item data and fees estimate
- Provides sales commission and FBA fee calculations

**ProductInfo** (`ProductInfoFetcher.gs`)
- Value object representing product information
- Contains: asin, title, imageUrl, releaseDate, size, weight, salesCommission, fbaFee
- Provides `toObject()` method for serialization

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

## Configuration

### API Keys Setup

The ProductInfoFetcher requires API credentials stored in Script Properties:

1. Go to Project Settings > Script Properties in the Apps Script editor
2. Add the following properties:
   - `KEEPA_API_KEY`: Your Keepa API key
   - `SP_API_REFRESH_TOKEN`: Amazon SP-API refresh token
   - `SP_API_CLIENT_ID`: Amazon SP-API client ID
   - `SP_API_CLIENT_SECRET`: Amazon SP-API client secret

### Usage Example

```javascript
const fetcher = new ProductInfoFetcher(keepaApiKey, spApiConfig);
const productInfo = fetcher.fetchProductInfo('B08N5WRWNW', 15.99);

// Access product data
console.log(productInfo.title);
console.log(productInfo.imageUrl);
console.log(productInfo.salesCommission);
console.log(productInfo.fbaFee);
```

## Key Constraints

- Code runs in Google Apps Script runtime (similar to ES6 JavaScript but with GAS-specific APIs)
- Must use `SpreadsheetApp` API for spreadsheet operations
- Uses `UrlFetchApp` for external API calls
- No npm packages or external dependencies available
- All code must be in `.gs` files
- Class syntax is supported but some modern ES features may not be available
- API rate limits: Keepa has rate limits per API key, add delays between requests if needed
