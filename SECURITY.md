# Privacy and vulnerability reports

Never post credentials or personal records in public issues. Use the repository's
private vulnerability reporting channel if available; otherwise ask for a private
contact route without publishing exploit secrets.

The core makes no network calls. It stores plain local files, not encrypted records.
Git ignores common runtime folders but they can be force-added. Review staged changes
and run the public-source check before publishing. That check is narrow, not a full
secret scanner. Third-party assistants/connectors have separate data and permission
policies; local files may be transmitted when you permit a remote model to read them.
