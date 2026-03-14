package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
)

const (
	baseURL = "https://app.loops.so/api/trpc"
)

var (
	action    = flag.String("action", "", "Action: status, unsubscribe, resubscribe")
	emailID   = flag.String("emailId", "", "Email ID from the unsubscribe link")
	token     = flag.String("token", "", "Unsubscribe token from the unsubscribe link")
	mailingID = flag.String("mailingListId", "", "Optional: Specific mailing list ID (not required for global)")
	format    = flag.String("format", "text", "Output format: text, json")
)

// API Response structures
type TRPCResponse struct {
	Result *TRPCResult `json:"result,omitempty"`
	Error  *TRPCError  `json:"error,omitempty"`
}

type TRPCResult struct {
	Data json.RawMessage `json:"data"`
}

type TRPCError struct {
	JSON struct {
		Message string `json:"message"`
		Code    string `json:"code"`
	} `json:"json"`
}

type SubscriptionData struct {
	SubscriptionsPreferences     []SubscriptionPreference `json:"subscriptionsPreferences"`
	MailingListsAvailableToThisUser []MailingList          `json:"mailingListsAvailableToThisUser"`
}

type SubscriptionPreference struct {
	MailingListID string `json:"mailingListId"`
	Subscribed    bool   `json:"subscribed"`
}

type MailingList struct {
	ID          string `json:"id"`
	FriendlyName string `json:"friendlyName"`
	Description string `json:"description"`
	ColorScheme string `json:"colorScheme"`
	IsPublic    bool   `json:"isPublic"`
}

func main() {
	flag.Parse()

	if *emailID == "" || *token == "" {
		fmt.Fprintln(os.Stderr, "Error: --emailId and --token are required")
		flag.Usage()
		os.Exit(1)
	}

	var err error
	switch *action {
	case "status":
		err = getSubscriptionStatus()
	case "unsubscribe":
		err = toggleSubscription(false)
	case "resubscribe":
		err = toggleSubscription(true)
	case "":
		fmt.Fprintln(os.Stderr, "Error: --action is required (status, unsubscribe, resubscribe)")
		flag.Usage()
		os.Exit(1)
	default:
		fmt.Fprintf(os.Stderr, "Error: unknown action '%s'\n", *action)
		flag.Usage()
		os.Exit(1)
	}

	if err != nil {
		fmt.Fprintln(os.Stderr, "Error:", err)
		os.Exit(1)
	}
}

func getSubscriptionStatus() error {
	input := map[string]string{
		"emailId":         *emailID,
		"unsubscribeToken": *token,
	}

	inputJSON, err := json.Marshal(input)
	if err != nil {
		return fmt.Errorf("failed to marshal input: %w", err)
	}

	encoded := url.QueryEscape(string(inputJSON))
	reqURL := fmt.Sprintf("%s/subscriptionCenter.fetchSubscriptionData?input={\"json\":%s}", baseURL, encoded)

	resp, err := http.Get(reqURL)
	if err != nil {
		return fmt.Errorf("failed to make request: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read response: %w", err)
	}

	if *format == "json" {
		fmt.Println(string(body))
		return nil
	}

	var trpcResp TRPCResponse
	if err := json.Unmarshal(body, &trpcResp); err != nil {
		return fmt.Errorf("failed to parse response: %w", err)
	}

	if trpcResp.Error != nil {
		return fmt.Errorf("API error: %s", trpcResp.Error.JSON.Message)
	}

	var subData SubscriptionData
	if err := json.Unmarshal(trpcResp.Result.Data, &subData); err != nil {
		return fmt.Errorf("failed to parse subscription data: %w", err)
	}

	fmt.Println("=== Subscription Status ===")
	fmt.Printf("Mailing lists available: %d\n", len(subData.MailingListsAvailableToThisUser))
	fmt.Println()

	for _, list := range subData.MailingListsAvailableToThisUser {
		// Check if subscribed
		subscribed := true
		for _, pref := range subData.SubscriptionsPreferences {
			if pref.MailingListID == list.ID {
				subscribed = pref.Subscribed
				break
			}
		}

		status := "✓ Subscribed"
		if !subscribed {
			status = "✗ Unsubscribed"
		}

		fmt.Printf("[%s] %s\n", status, list.FriendlyName)
		if list.Description != "" {
			fmt.Printf("    %s\n", list.Description)
		}
		fmt.Println()
	}

	return nil
}

func toggleSubscription(newStatus bool) error {
	input := map[string]interface{}{
		"emailId":             *emailID,
		"newSubscriptionStatus": newStatus,
		"unsubscribeToken":    *token,
	}

	// Use handleToggleGlobalUnsubscribe for global unsubscribe/resubscribe
	// For specific mailing lists, you'd use handleToggleSubscribe with mailingListId
	inputJSON, err := json.Marshal(input)
	if err != nil {
		return fmt.Errorf("failed to marshal input: %w", err)
	}

	reqBody := fmt.Sprintf(`{"json":%s}`, string(inputJSON))

	req, err := http.NewRequest("POST", baseURL+"/subscriptionCenter.handleToggleGlobalUnsubscribe", bytes.NewBufferString(reqBody))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to make request: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read response: %w", err)
	}

	if *format == "json" {
		fmt.Println(string(body))
		return nil
	}

	var trpcResp TRPCResponse
	if err := json.Unmarshal(body, &trpcResp); err != nil {
		return fmt.Errorf("failed to parse response: %w", err)
	}

	if trpcResp.Error != nil {
		return fmt.Errorf("API error: %s (code: %s)", trpcResp.Error.JSON.Message, trpcResp.Error.JSON.Code)
	}

	actionWord := "unsubscribed"
	if newStatus {
		actionWord = "resubscribed"
	}
	fmt.Printf("Successfully %s from all emails!\n", actionWord)

	return nil
}

// Helper to parse unsubscribe link
// Format: https://app.loops.so/unsubscribe/{emailId}/{token}
func ParseUnsubscribeLink(link string) (emailID, token string, err error) {
	// Remove trailing slash
	link = strings.TrimSuffix(link, "/")

	parts := strings.Split(link, "/")
	if len(parts) < 2 {
		return "", "", fmt.Errorf("invalid unsubscribe link format")
	}

	// Find the last two parts
	n := len(parts)
	if n < 2 {
		return "", "", fmt.Errorf("invalid unsubscribe link: too few parts")
	}

	// The emailId and token are the last two URL segments
	// But they might be URL encoded, so we need to handle that
	token = parts[n-1]
	emailID = parts[n-2]

	// URL decode
	emailID, err = url.QueryUnescape(emailID)
	if err != nil {
		return "", "", fmt.Errorf("failed to decode emailId: %w", err)
	}

	token, err = url.QueryUnescape(token)
	if err != nil {
		return "", "", fmt.Errorf("failed to decode token: %w", err)
	}

	return emailID, token, nil
}