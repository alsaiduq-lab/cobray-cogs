# DLM - DuelLinksMeta (...and MasterDuelMeta too) Cog

## Overview

This repository contains a Red Discord Bot cog named **DLM** (DuelLinksMeta). It offers a variety of features and commands for managing Duel Links data, including:

- Card lookups with automatic embed generation.
- Article commands and deck commands.
- Event and tournament management.
- Meta commands for statistical or strategy insights.

## Main Components

1. **CardRegistry**

   - Manages a registry of card data.
   - Provides methods to search and fetch card details.

2. **InteractionHandler**

   - Handles slash interactions, and user inputs.
   - Builds Discord embeds for displaying card details, decks, etc.

3. **UserConfig**

   - Stores and retrieves user-specific settings (e.g., format preferences, auto-search toggle).

4. **Command Modules**
   - ArticleCommands: Retrieve links or content for DLM articles.
   - CardCommands: Commands for card lookup, quick reference.
   - DeckCommands: Manage deck references.
   - EventCommands: Keep track of Duel Links events.
   - MetaCommands: Access meta reports and advanced stats.
   - TournamentCommands: Interfaces with DLM’s tournament data.

## Features

- Automatic detection of card names in Discord messages and replying with card embed(s).
- A background "update loop" to periodically refresh registry data.
- User-friendly error handling for common command issues.
- Application command integration (slash commands) if desired.

## Usage

Use the `[p]dlm` command group to access subcommands:

- `[p]dlm cards <card_name>`: Retrieve detailed embed of the specified card.
- `[p]dlm meta` or `[p]dlm events`: Additional subcommands for meta or event data.
- (And other subcommands defined within the included modules.)

In servers where **auto-search** is enabled, simply **mention a card name** in a message to receive an embed with the card details.

## Contribution

Feel free to fork this repository, open issues, or make pull requests to enhance the functionality of the DLM cog.

## License

This project is licensed under the [MIT License](https://opensource.org/licenses/MIT). Please see the [LICENSE](LICENSE) file for details.
