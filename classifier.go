package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/anthropics/anthropic-sdk-go"
	"github.com/anthropics/anthropic-sdk-go/option"
	_ "github.com/mattn/go-sqlite3"
)

type Config struct {
	AnthropicAPIKey string `json:"anthropic_api_key"`
}

type Transaction struct {
	ID          int
	Date        string
	Description string
	Amount      float64
	Category    sql.NullString
}

type ClassificationResult struct {
	ID       int
	Category string
	Error    error
}

var categories = []string{
	"software",
	"professional membership",
	"technical library",
	"magazines and journals",
	"training",
	"not work related",
	"other",
}

func loadConfig(configPath string) (*Config, error) {
	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read config: %w", err)
	}

	var config Config
	if err := json.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("failed to parse config: %w", err)
	}

	return &config, nil
}

func getUnclassifiedTransactions(db *sql.DB) ([]Transaction, error) {
	query := `
		SELECT id, trans_date, description, amount, category
		FROM transactions
		WHERE ai_classified = 0 OR ai_classified IS NULL
		ORDER BY trans_date DESC
	`

	rows, err := db.Query(query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var transactions []Transaction
	for rows.Next() {
		var t Transaction
		if err := rows.Scan(&t.ID, &t.Date, &t.Description, &t.Amount, &t.Category); err != nil {
			return nil, err
		}
		transactions = append(transactions, t)
	}

	return transactions, rows.Err()
}

func classifyTransaction(ctx context.Context, client *anthropic.Client, desc string, amount float64) (string, error) {
	prompt := fmt.Sprintf(`Given this credit card transaction, classify it into one of these categories for tax deduction purposes:

Categories:
- "software": Software purchases, SaaS subscriptions, development tools
- "professional membership": Professional organization memberships, certifications
- "technical library": Books, technical publications, O'Reilly, Manning, etc.
- "magazines and journals": Technical magazines, IEEE, ACM subscriptions
- "training": Online courses, conferences, workshops, training materials
- "not work related": Personal purchases, food, entertainment, general shopping
- "other": Work-related but doesn't fit other categories

Transaction:
Description: %s
Amount: $%.2f

Context: This is for an OT cybersecurity professional in industrial control systems.

Respond with ONLY the category name in lowercase, nothing else.`, desc, amount)

	maxTokens := int64(50)
	message, err := client.Messages.New(ctx, anthropic.MessageNewParams{
		Model:     anthropic.F("claude-sonnet-4-20250514"),
		MaxTokens: anthropic.F(maxTokens),
		Messages: anthropic.F([]anthropic.MessageParam{
			anthropic.NewUserMessage(anthropic.NewTextBlock(prompt)),
		}),
	})

	if err != nil {
		return "", err
	}

	if len(message.Content) == 0 {
		return "", fmt.Errorf("empty response")
	}

	category := strings.TrimSpace(strings.Trim(message.Content[0].Text, `"`))
	category = strings.ToLower(category)

	// Validate category
	for _, valid := range categories {
		if category == valid {
			return category, nil
		}
	}

	return "other", nil
}

func classifyWorker(ctx context.Context, client *anthropic.Client, jobs <-chan Transaction, results chan<- ClassificationResult, wg *sync.WaitGroup) {
	defer wg.Done()

	for transaction := range jobs {
		select {
		case <-ctx.Done():
			return
		default:
			category, err := classifyTransaction(ctx, client, transaction.Description, transaction.Amount)
			results <- ClassificationResult{
				ID:       transaction.ID,
				Category: category,
				Error:    err,
			}
		}
	}
}

func updateTransactionCategory(db *sql.DB, id int, category string) error {
	_, err := db.Exec(`
		UPDATE transactions 
		SET category = ?, ai_classified = 1 
		WHERE id = ?
	`, category, id)
	return err
}

func main() {
	dbPath := flag.String("d", "", "Path to SQLite database file (required)")
	configPath := flag.String("c", "config.json", "Path to config file")
	workers := flag.Int("w", 10, "Number of concurrent workers")
	dryRun := flag.Bool("dry-run", false, "Show what would be classified without updating database")
	flag.Parse()

	if *dbPath == "" {
		log.Fatal("Error: -d (database path) is required")
	}

	// Load config
	config, err := loadConfig(*configPath)
	if err != nil {
		log.Fatalf("Error loading config: %v", err)
	}

	if config.AnthropicAPIKey == "" {
		log.Fatal("Error: anthropic_api_key not found in config file")
	}

	// Open database
	db, err := sql.Open("sqlite3", *dbPath)
	if err != nil {
		log.Fatalf("Error opening database: %v", err)
	}
	defer db.Close()

	// Get unclassified transactions
	transactions, err := getUnclassifiedTransactions(db)
	if err != nil {
		log.Fatalf("Error fetching transactions: %v", err)
	}

	if len(transactions) == 0 {
		fmt.Println("✓ No unclassified transactions found")
		return
	}

	totalCount := len(transactions)
	fmt.Printf("Found %d unclassified transactions\n", totalCount)
	fmt.Printf("Using %d concurrent workers\n\n", *workers)

	if *dryRun {
		fmt.Println("DRY RUN MODE - No database updates will be made\n")
	}

	// Create Anthropic client
	client := anthropic.NewClient(
		option.WithAPIKey(config.AnthropicAPIKey),
	)

	// Create channels and worker pool
	ctx := context.Background()
	jobs := make(chan Transaction, len(transactions))
	results := make(chan ClassificationResult, len(transactions))

	var wg sync.WaitGroup

	// Start workers
	for i := 0; i < *workers; i++ {
		wg.Add(1)
		go classifyWorker(ctx, client, jobs, results, &wg)
	}

	// Send jobs
	for _, t := range transactions {
		jobs <- t
	}
	close(jobs)

	// Wait for workers to finish
	go func() {
		wg.Wait()
		close(results)
	}()

	// Process results with counter
	startTime := time.Now()
	var processed int64
	classified := 0
	failed := 0

	for result := range results {
		current := atomic.AddInt64(&processed, 1)
		
		if result.Error != nil {
			fmt.Printf("✗ (%d/%d) ID %d failed: %v\n", current, totalCount, result.ID, result.Error)
			failed++
			continue
		}

		// Find the transaction for display
		var trans Transaction
		for _, t := range transactions {
			if t.ID == result.ID {
				trans = t
				break
			}
		}

		fmt.Printf("✓ (%d/%d) ID %d: %s → %s\n", 
			current, totalCount, result.ID, truncate(trans.Description, 45), result.Category)

		if !*dryRun {
			if err := updateTransactionCategory(db, result.ID, result.Category); err != nil {
				fmt.Printf("  Warning: Failed to update database: %v\n", err)
				failed++
			} else {
				classified++
			}
		} else {
			classified++
		}
	}

	elapsed := time.Since(startTime)

	fmt.Printf("\n%s\n", strings.Repeat("=", 60))
	if *dryRun {
		fmt.Printf("DRY RUN COMPLETE\n")
		fmt.Printf("Would classify: %d transactions\n", classified)
	} else {
		fmt.Printf("CLASSIFICATION COMPLETE\n")
		fmt.Printf("Successfully classified: %d transactions\n", classified)
	}
	fmt.Printf("Failed: %d transactions\n", failed)
	fmt.Printf("Time elapsed: %s\n", elapsed)
	fmt.Printf("Rate: %.1f transactions/second\n", float64(totalCount)/elapsed.Seconds())
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen-3] + "..."
}