package recommender

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math"
	"math/rand"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/joho/godotenv"
	"github.com/lithammer/fuzzysearch/fuzzy"
)

// Constants and Configuration
const (
	DefaultFuzzyThreshold = 70
	FuzzyMaxCandidates    = 250
)

var (
	FavoritesFile     = "favorites.json"
	MoviesCSVPath     = "movies_cleaned.csv"
	RatingsCSVPath    = "ratings_cleaned.csv"
	LastSaveError     string
	Movies            []Movie
	Favorites         []Favorite
	FavoritesSet      map[string]bool // key: "name|year"
	Mutex             sync.RWMutex
	YearRegexp        = regexp.MustCompile(`\((\d{4})\)`)
	CleanTitleRegexp  = regexp.MustCompile(`\s*\(\d{4}\)$`)
	BuiltinMovies     = []Movie{
		{Name: "Superman", Year: 1978, Category: "Blockbuster", Genre: "Action", BoxOfficeMillions: 134.2, Rating: 7.9},
		{Name: "The Avengers", Year: 2012, Category: "Blockbuster", Genre: "Action", BoxOfficeMillions: 1518.8, Rating: 8.4},
		{Name: "Man From Toronto", Year: 2022, Category: "Streaming", Genre: "Action/Comedy", BoxOfficeMillions: 12.3, Rating: 6.1},
		{Name: "Black Widow", Year: 2021, Category: "Blockbuster", Genre: "Action", BoxOfficeMillions: 379.8, Rating: 6.8},
		{Name: "Shazam!", Year: 2019, Category: "Blockbuster", Genre: "Family/Fantasy", BoxOfficeMillions: 364.6, Rating: 7.1},
		{Name: "John Wick", Year: 2014, Category: "Action Franchise", Genre: "Action/Thriller", BoxOfficeMillions: 86.0, Rating: 7.4},
		{Name: "Spider-Man: No Way Home", Year: 2021, Category: "Blockbuster", Genre: "Action/Adventure", BoxOfficeMillions: 1932.0, Rating: 8.1},
		{Name: "Inception", Year: 2010, Category: "Prestige", Genre: "Sci-Fi", BoxOfficeMillions: 829.9, Rating: 8.8},
		{Name: "The Godfather", Year: 1972, Category: "Classic", Genre: "Crime/Drama", BoxOfficeMillions: 246.1, Rating: 9.2},
		{Name: "Parasite", Year: 2019, Category: "Indie", Genre: "Thriller/Drama", BoxOfficeMillions: 258.8, Rating: 8.6},
		{Name: "La La Land", Year: 2016, Category: "Musical", Genre: "Musical/Romance", BoxOfficeMillions: 446.1, Rating: 8.0},
		{Name: "Toy Story", Year: 1995, Category: "Animation", Genre: "Family/Animation", BoxOfficeMillions: 373.6, Rating: 8.3},
		{Name: "The Dark Knight", Year: 2008, Category: "Prestige", Genre: "Action/Crime", BoxOfficeMillions: 1004.9, Rating: 9.0},
		{Name: "Forrest Gump", Year: 1994, Category: "Classic", Genre: "Drama/Romance", BoxOfficeMillions: 678.2, Rating: 8.8},
		{Name: "The Shawshank Redemption", Year: 1994, Category: "Classic", Genre: "Drama", BoxOfficeMillions: 58.3, Rating: 9.3},
		{Name: "Interstellar", Year: 2014, Category: "Prestige", Genre: "Sci-Fi/Drama", BoxOfficeMillions: 677.5, Rating: 8.6},
		{Name: "Get Out", Year: 2017, Category: "Indie", Genre: "Horror/Thriller", BoxOfficeMillions: 255.4, Rating: 7.7},
		{Name: "The Matrix", Year: 1999, Category: "Sci-Fi", Genre: "Action/Sci-Fi", BoxOfficeMillions: 463.5, Rating: 8.7},
		{Name: "Titanic", Year: 1997, Category: "Romance/Blockbuster", Genre: "Romance/Drama", BoxOfficeMillions: 2187.5, Rating: 7.8},
		{Name: "Spirited Away", Year: 2001, Category: "Animation", Genre: "Fantasy/Animation", BoxOfficeMillions: 355.5, Rating: 8.6},
		{Name: "The Social Network", Year: 2010, Category: "Drama", Genre: "Drama/Biography", BoxOfficeMillions: 224.9, Rating: 7.7},
		{Name: "Mad Max: Fury Road", Year: 2015, Category: "Action", Genre: "Action/Adventure", BoxOfficeMillions: 378.9, Rating: 8.1},
		{Name: "City of God", Year: 2002, Category: "Indie", Genre: "Crime/Drama", BoxOfficeMillions: 30.6, Rating: 8.6},
		{Name: "Coco", Year: 2017, Category: "Animation", Genre: "Family/Animation", BoxOfficeMillions: 807.1, Rating: 8.4},
	}
)

// Types
type Movie struct {
	Name               string   `json:"name"`
	Year               int      `json:"year"`
	Category           string   `json:"category"`
	Genre              string   `json:"genre"`
	BoxOfficeMillions float64  `json:"box_office_millions"`
	Rating             float64  `json:"rating"`
	MovieID            int      `json:"movieId,omitempty"`
	AllGenres          []string `json:"all_genres,omitempty"`
	SearchText         string   `json:"_search_text,omitempty"`
	Tokens             []string `json:"_tokens,omitempty"`
}

type Favorite struct {
	Name string `json:"name"`
	Year int    `json:"year"`
}

type GenreCount struct {
	Genre string `json:"genre"`
	Count int    `json:"count"`
}

type CategoryCount struct {
	Category string `json:"category"`
	Count    int    `json:"count"`
}

// Initialization Logic
func init() {
	godotenv.Load()
	if val := os.Getenv("FAVORITES_FILE"); val != "" {
		FavoritesFile = val
	}
	if val := os.Getenv("MOVIES_CSV_PATH"); val != "" {
		MoviesCSVPath = val
	}
	if val := os.Getenv("RATINGS_CSV_PATH"); val != "" {
		RatingsCSVPath = val
	}
	rand.Seed(time.Now().UnixNano())
}

func InitializeMovieDataset() {
	Mutex.Lock()
	defer Mutex.Unlock()

	Movies = append([]Movie{}, BuiltinMovies...)

	csvMovies := integrateCSVData()
	existing := make(map[string]bool)
	for _, m := range Movies {
		existing[strings.ToLower(m.Name)+"|"+strconv.Itoa(m.Year)] = true
	}

	for _, m := range csvMovies {
		key := strings.ToLower(m.Name) + "|" + strconv.Itoa(m.Year)
		if !existing[key] {
			Movies = append(Movies, m)
			existing[key] = true
		}
	}

	for i := range Movies {
		ensureSearchFields(&Movies[i])
	}
}

func ensureSearchFields(m *Movie) {
	name := strings.ToLower(m.Name)
	genre := strings.ToLower(m.Genre)
	category := strings.ToLower(m.Category)
	m.SearchText = strings.TrimSpace(fmt.Sprintf("%s %s %s", name, genre, category))
	
	tokens := regexp.MustCompile(`[\s/+,]`).Split(m.SearchText, -1)
	m.Tokens = nil
	for _, t := range tokens {
		if t != "" {
			m.Tokens = append(m.Tokens, t)
		}
	}
}

// CSV Loader Logic (Ported from csv_loader.py)
func integrateCSVData() []Movie {
	movies := loadMoviesFromCSV(MoviesCSVPath)
	ratings := loadRatingsFromCSV(RatingsCSVPath)

	for i := range movies {
		if r, ok := ratings[movies[i].MovieID]; ok && len(r) > 0 {
			var sum float64
			for _, v := range r {
				sum += v
			}
			movies[i].Rating = mathRound(sum/float64(len(r)), 1)
		}
	}
	return movies
}

func loadMoviesFromCSV(path string) []Movie {
	var results []Movie
	file, err := os.Open(path)
	if err != nil {
		log.Printf("Movies CSV file not found: %s", path)
		return results
	}
	defer file.Close()

	reader := csv.NewReader(file)
	header, err := reader.Read()
	if err != nil {
		return results
	}

	colIdx := make(map[string]int)
	for i, name := range header {
		colIdx[name] = i
	}

	for {
		record, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			continue
		}

		movieID, _ := strconv.Atoi(record[colIdx["movieId"]])
		title := strings.TrimSpace(record[colIdx["title"]])
		yearStr := strings.TrimSpace(record[colIdx["year"]])
		genresRaw := strings.TrimSpace(record[colIdx["genres"]])

		year := 2000
		if y, err := strconv.Atoi(yearStr); err == nil {
			year = y
		} else {
			if match := YearRegexp.FindStringSubmatch(title); len(match) > 1 {
				year, _ = strconv.Atoi(match[1])
			}
		}

		cleanTitle := CleanTitleRegexp.ReplaceAllString(title, "")
		cleanTitle = strings.TrimSpace(cleanTitle)

		var allGenres []string
		for _, g := range strings.Split(genresRaw, "|") {
			g = strings.TrimSpace(g)
			if g != "" && g != "(no genres listed)" {
				allGenres = append(allGenres, g)
			}
		}

		category := determineCategory(allGenres, year)
		primaryGenre := "Unknown"
		if len(allGenres) > 0 {
			primaryGenre = allGenres[0]
		}

		results = append(results, Movie{
			Name:              cleanTitle,
			Year:              year,
			Category:          category,
			Genre:             primaryGenre,
			BoxOfficeMillions: 0.0,
			Rating:            0.0,
			MovieID:           movieID,
			AllGenres:         allGenres,
		})
	}
	return results
}

func loadRatingsFromCSV(path string) map[int][]float64 {
	results := make(map[int][]float64)
	file, err := os.Open(path)
	if err != nil {
		return results
	}
	defer file.Close()

	reader := csv.NewReader(file)
	header, err := reader.Read()
	if err != nil {
		return results
	}

	colIdx := make(map[string]int)
	for i, name := range header {
		colIdx[name] = i
	}

	for {
		record, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			continue
		}

		movieID, _ := strconv.Atoi(record[colIdx["movieId"]])
		rating, _ := strconv.ParseFloat(record[colIdx["rating"]], 64)
		results[movieID] = append(results[movieID], rating)
	}
	return results
}

func determineCategory(genres []string, year int) string {
	if len(genres) == 0 {
		return "Other"
	}
	lower := make([]string, len(genres))
	for i, g := range genres {
		lower[i] = strings.ToLower(g)
	}

	contains := func(list []string, targets ...string) bool {
		for _, item := range list {
			for _, t := range targets {
				if item == t {
					return true
				}
			}
		}
		return false
	}

	if contains(lower, "animation", "children") {
		return "Animation"
	} else if contains(lower, "action", "adventure") {
		if year >= 2010 {
			return "Blockbuster"
		}
		return "Classic"
	} else if contains(lower, "sci-fi", "fantasy") {
		return "Prestige"
	} else if contains(lower, "drama", "romance") {
		return "Classic"
	} else if contains(lower, "comedy") {
		if year >= 2015 {
			return "Streaming"
		}
		return "Classic"
	} else if contains(lower, "thriller", "crime", "mystery", "horror") {
		return "Indie"
	} else if contains(lower, "documentary", "biography") {
		return "Prestige"
	}
	return "Other"
}

// Favorites Management
func LoadFavorites(path string) {
	Mutex.Lock()
	defer Mutex.Unlock()

	FavoritesSet = make(map[string]bool)
	Favorites = nil

	err := withFileLock(path, func() error {
		file, err := os.Open(path)
		if err != nil {
			if os.IsNotExist(err) {
				return nil
			}
			return err
		}
		defer file.Close()

		if err := json.NewDecoder(file).Decode(&Favorites); err != nil {
			return err
		}
		for _, f := range Favorites {
			FavoritesSet[strings.ToLower(f.Name)+"|"+strconv.Itoa(f.Year)] = true
		}
		return nil
	})
	if err != nil {
		log.Printf("Failed to load favorites: %v", err)
	}
}

func SaveFavorites(path string) bool {
	Mutex.RLock()
	defer Mutex.RUnlock()

	err := withFileLock(path, func() error {
		return atomicWriteJSON(path, Favorites)
	})
	if err != nil {
		LastSaveError = fmt.Sprintf("Failed to save favorites: %v", err)
		return false
	}
	LastSaveError = ""
	return true
}

func AddFavorite(name string, year int, path string) bool {
	nameLower := strings.ToLower(name)
	key := nameLower + "|" + strconv.Itoa(year)

	Mutex.RLock()
	existsInDataset := false
	for _, m := range Movies {
		if strings.ToLower(m.Name) == nameLower && m.Year == year {
			existsInDataset = true
			break
		}
	}
	Mutex.RUnlock()

	if !existsInDataset {
		log.Printf("Movie not found in dataset: %s (%d)", name, year)
		return false
	}

	Mutex.Lock()
	defer Mutex.Unlock()

	err := withFileLock(path, func() error {
		var current []Favorite
		if file, err := os.Open(path); err == nil {
			json.NewDecoder(file).Decode(&current)
			file.Close()
		}

		for _, f := range current {
			if strings.ToLower(f.Name) == nameLower && f.Year == year {
				return nil // already exists
			}
		}

		current = append(current, Favorite{Name: name, Year: year})
		if err := atomicWriteJSON(path, current); err != nil {
			return err
		}
		Favorites = current
		if FavoritesSet == nil {
			FavoritesSet = make(map[string]bool)
		}
		FavoritesSet[key] = true
		return nil
	})

	if err != nil {
		LastSaveError = fmt.Sprintf("Failed to add favorite: %v", err)
		return false
	}
	return true
}

func RemoveFavorite(name string, year int, path string) bool {
	nameLower := strings.ToLower(name)
	key := nameLower + "|" + strconv.Itoa(year)

	Mutex.Lock()
	defer Mutex.Unlock()

	err := withFileLock(path, func() error {
		var current []Favorite
		if file, err := os.Open(path); err == nil {
			json.NewDecoder(file).Decode(&current)
			file.Close()
		}

		var updated []Favorite
		found := false
		for _, f := range current {
			if strings.ToLower(f.Name) == nameLower && f.Year == year {
				found = true
				continue
			}
			updated = append(updated, f)
		}

		if !found {
			return nil
		}

		if err := atomicWriteJSON(path, updated); err != nil {
			return err
		}
		Favorites = updated
		delete(FavoritesSet, key)
		return nil
	})

	if err != nil {
		LastSaveError = fmt.Sprintf("Failed to remove favorite: %v", err)
		return false
	}
	return true
}

func GetFavoriteMovies() []Movie {
	Mutex.RLock()
	defer Mutex.RUnlock()

	lookup := make(map[string]Movie)
	for _, m := range Movies {
		lookup[strings.ToLower(m.Name)+"|"+strconv.Itoa(m.Year)] = m
	}

	var results []Movie
	for _, f := range Favorites {
		key := strings.ToLower(f.Name) + "|" + strconv.Itoa(f.Year)
		if m, ok := lookup[key]; ok {
			results = append(results, m)
		} else {
			results = append(results, Movie{
				Name: f.Name,
				Year: f.Year,
			})
		}
	}
	return results
}

// Atomic Write and Locking Helpers
func atomicWriteJSON(path string, data interface{}) error {
	tmpFile, err := os.CreateTemp(filepath.Dir(path), "."+filepath.Base(path)+".*.tmp")
	if err != nil {
		return err
	}
	defer os.Remove(tmpFile.Name())

	enc := json.NewEncoder(tmpFile)
	enc.SetIndent("", "  ")
	if err := enc.Encode(data); err != nil {
		tmpFile.Close()
		return err
	}

	if err := tmpFile.Sync(); err != nil {
		tmpFile.Close()
		return err
	}
	if err := tmpFile.Close(); err != nil {
		return err
	}

	return os.Rename(tmpFile.Name(), path)
}

func withFileLock(path string, fn func() error) error {
	lockPath := path + ".lock"
	f, err := os.OpenFile(lockPath, os.O_CREATE|os.O_RDWR, 0666)
	if err != nil {
		return err
	}
	defer f.Close()

	if err := syscall.Flock(int(f.Fd()), syscall.LOCK_EX); err != nil {
		return err
	}
	defer syscall.Flock(int(f.Fd()), syscall.LOCK_UN)

	return fn()
}

// Search and Recommendation Logic
type Match struct {
	Movie    Movie
	Priority int
}

func FindMatches(query string, maxResults int, enableFuzzy bool, threshold int, genre, category string, minRating float64, year, yearFrom, yearTo int, sortBy string) []Movie {
	Mutex.RLock()
	defer Mutex.RUnlock()

	qLower := strings.ToLower(sanitizeQuery(query, 100))
	var filtered []Movie

	for _, m := range Movies {
		if genre != "" && !strings.Contains(strings.ToLower(m.Genre), strings.ToLower(genre)) {
			found := false
			for _, ag := range m.AllGenres {
				if strings.Contains(strings.ToLower(ag), strings.ToLower(genre)) {
					found = true
					break
				}
			}
			if !found {
				continue
			}
		}
		if category != "" && !strings.Contains(strings.ToLower(m.Category), strings.ToLower(category)) {
			continue
		}
		if minRating > 0 && m.Rating < minRating {
			continue
		}
		if year > 0 && m.Year != year {
			continue
		}
		if yearFrom > 0 && m.Year < yearFrom {
			continue
		}
		if yearTo > 0 && m.Year > yearTo {
			continue
		}
		filtered = append(filtered, m)
	}

	var matchesWithPriority []Match

	if qLower == "" {
		if genre != "" || category != "" || minRating > 0 || year > 0 || yearFrom > 0 || yearTo > 0 {
			for _, m := range filtered {
				matchesWithPriority = append(matchesWithPriority, Match{Movie: m, Priority: 1000})
			}
		}
	} else {
		if y, err := strconv.Atoi(qLower); err == nil {
			for _, m := range filtered {
				if m.Year == y {
					matchesWithPriority = append(matchesWithPriority, Match{Movie: m, Priority: 1000})
				}
			}
		} else {
			tokens := regexp.MustCompile(`[\s/+,]`).Split(qLower, -1)
			for _, m := range filtered {
				name := strings.ToLower(m.Name)
				genreV := strings.ToLower(m.Genre)
				categoryV := strings.ToLower(m.Category)

				priority := 0
				for _, t := range tokens {
					if t == "" {
						continue
					}
					// token-level match -> highest priority
					isToken := false
					for _, mt := range m.Tokens {
						if mt == t {
							isToken = true
							break
						}
					}
					if isToken {
						priority = 1000
						break
					}
					// startswith on name -> high priority
					if strings.HasPrefix(name, t) {
						priority = 900
						break
					}
					// exact substring match -> medium priority
					if strings.Contains(name, t) || strings.Contains(genreV, t) || strings.Contains(categoryV, t) {
						priority = 800
						break
					}
				}
				if priority > 0 {
					matchesWithPriority = append(matchesWithPriority, Match{Movie: m, Priority: priority})
				}
			}
		}
	}

	// Fuzzy Matching
	if enableFuzzy && qLower != "" {
		existing := make(map[string]bool)
		for _, mp := range matchesWithPriority {
			existing[mp.Movie.Name+"|"+strconv.Itoa(mp.Movie.Year)] = true
		}

		var candidates []Movie
		for _, m := range filtered {
			if !existing[m.Name+"|"+strconv.Itoa(m.Year)] {
				candidates = append(candidates, m)
			}
		}

		sort.Slice(candidates, func(i, j int) bool {
			if candidates[i].Rating != candidates[j].Rating {
				return candidates[i].Rating > candidates[j].Rating
			}
			return candidates[i].BoxOfficeMillions > candidates[j].BoxOfficeMillions
		})

		limit := FuzzyMaxCandidates
		if len(candidates) < limit {
			limit = len(candidates)
		}
		candidatesSubset := candidates[:limit]

		for _, m := range candidatesSubset {
			bestScore := 0
			for _, token := range append([]string{strings.ToLower(m.Name)}, m.Tokens...) {
				if fuzzy.Match(qLower, token) {
					dist := fuzzy.LevenshteinDistance(qLower, token)
					score := 100 - (dist * 100 / len(token))
					if score > bestScore {
						bestScore = score
					}
				}
			}

			if bestScore >= threshold {
				matchesWithPriority = append(matchesWithPriority, Match{Movie: m, Priority: bestScore})
			}
		}
	}

	best := make(map[string]Match)
	for _, mp := range matchesWithPriority {
		key := mp.Movie.Name + "|" + strconv.Itoa(mp.Movie.Year)
		if existing, ok := best[key]; !ok || mp.Priority > existing.Priority {
			best[key] = mp
		}
	}

	var results []Movie
	for _, v := range best {
		results = append(results, v.Movie)
	}

	getPriority := func(m Movie) int {
		return best[m.Name+"|"+strconv.Itoa(m.Year)].Priority
	}

	sort.Slice(results, func(i, j int) bool {
		m1, m2 := results[i], results[j]
		p1, p2 := getPriority(m1), getPriority(m2)

		switch strings.ToLower(sortBy) {
		case "rating":
			if m1.Rating != m2.Rating {
				return m1.Rating > m2.Rating
			}
		case "box_office", "box_office_millions":
			if m1.BoxOfficeMillions != m2.BoxOfficeMillions {
				return m1.BoxOfficeMillions > m2.BoxOfficeMillions
			}
		case "year":
			if m1.Year != m2.Year {
				return m1.Year > m2.Year
			}
		}
		if p1 != p2 {
			return p1 > p2
		}
		if m1.Rating != m2.Rating {
			return m1.Rating > m2.Rating
		}
		return m1.BoxOfficeMillions > m2.BoxOfficeMillions
	})

	if maxResults > 0 && len(results) > maxResults {
		return results[:maxResults]
	}
	return results
}

// Utilities
func sanitizeQuery(q string, maxLength int) string {
	q = regexp.MustCompile(`[\x00-\x1f\x7f-\x9f]`).ReplaceAllString(q, "")
	q = strings.TrimSpace(q)
	if len(q) > maxLength {
		q = q[:maxLength]
	}
	return q
}

func mathRound(val float64, precision int) float64 {
	ratio := math.Pow(10, float64(precision))
	return math.Round(val*ratio) / ratio
}

func getAvailableGenres() []GenreCount {
	Mutex.RLock()
	defer Mutex.RUnlock()
	counts := make(map[string]int)
	for _, m := range Movies {
		tokens := regexp.MustCompile(`[\s/]+`).Split(m.Genre, -1)
		for _, t := range tokens {
			t = strings.TrimSpace(t)
			if t != "" {
				counts[t]++
			}
		}
	}
	var res []GenreCount
	for g, c := range counts {
		res = append(res, GenreCount{Genre: g, Count: c})
	}
	sort.Slice(res, func(i, j int) bool {
		if res[i].Count != res[j].Count {
			return res[i].Count > res[j].Count
		}
		return res[i].Genre < res[j].Genre
	})
	return res
}

func getAvailableCategories() []CategoryCount {
	Mutex.RLock()
	defer Mutex.RUnlock()
	counts := make(map[string]int)
	for _, m := range Movies {
		if m.Category != "" {
			counts[m.Category]++
		}
	}
	var res []CategoryCount
	for cat, count := range counts {
		res = append(res, CategoryCount{Category: cat, Count: count})
	}
	sort.Slice(res, func(i, j int) bool {
		if res[i].Count != res[j].Count {
			return res[i].Count > res[j].Count
		}
		return res[i].Category < res[j].Category
	})
	return res
}
