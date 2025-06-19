# Cursor IDE Language Rules

## Code Language Policy
1. **All source code** must be written exclusively in **English**:
   - Variable names, function names, class names
   - Code comments and documentation
   - String literals and user messages
   - Commit messages
   - Error messages and logging
   - API responses and JSON fields

## Communication Language Policy  
2. **Assistant responses** to the developer should use the **same language** the developer used in their query.

## Enforcement
3. The assistant must **never inject non-English languages** into code, even if the developer communicates in another language.
4. If existing code contains non-English text, it should be translated to English when modified.
5. All new code must follow English-only conventions regardless of the conversation language.