package utils

import "math"

// PointInPolygon checks if a point is inside a polygon using ray-casting algorithm
// All coordinates are normalized (0.0 - 1.0)
func PointInPolygon(x, y float64, polygon [][]float64) bool {
	n := len(polygon)
	if n < 3 {
		return false
	}

	inside := false
	j := n - 1
	for i := 0; i < n; i++ {
		xi, yi := polygon[i][0], polygon[i][1]
		xj, yj := polygon[j][0], polygon[j][1]

		if ((yi > y) != (yj > y)) && (x < (xj-xi)*(y-yi)/(yj-yi)+xi) {
			inside = !inside
		}
		j = i
	}

	return inside
}

// ComputeCentroid calculates the centroid of a polygon
func ComputeCentroid(vertices [][]float64) (float64, float64) {
	n := len(vertices)
	if n == 0 {
		return 0.0, 0.0
	}

	var cx, cy float64
	for _, v := range vertices {
		cx += v[0]
		cy += v[1]
	}
	return cx / float64(n), cy / float64(n)
}

// ParseVertices parses JSON vertices string into [][]float64
// This is a simple parser for comma-separated format like "[[0.1,0.2],[0.3,0.4]]"
func ParseVertices(verticesJSON string) [][]float64 {
	// Simple parsing for JSON array format
	// Format: [[0.1,0.2],[0.3,0.4],...]
	var result [][]float64
	var currentPair []float64
	var numStr string
	inArray := false
	inPair := false

	for i := 0; i < len(verticesJSON); i++ {
		c := verticesJSON[i]

		switch c {
		case '[':
			if !inArray {
				inArray = true
				currentPair = nil
			} else if !inPair {
				inPair = true
				numStr = ""
			}
		case ']':
			if inPair && numStr != "" {
				val := parseFloat(numStr)
				currentPair = append(currentPair, val)
				numStr = ""
			}
			if inPair && len(currentPair) == 2 {
				result = append(result, currentPair)
				currentPair = nil
				inPair = false
			} else if inArray && !inPair {
				inArray = false
			}
		case ',':
			if inPair && numStr != "" {
				val := parseFloat(numStr)
				currentPair = append(currentPair, val)
				numStr = ""
			}
		case ' ', '\t', '\n', '\r':
			// Skip whitespace
		default:
			if c >= '0' && c <= '9' || c == '.' || c == '-' {
				numStr += string(c)
			}
		}
	}

	return result
}

func parseFloat(s string) float64 {
	var result float64
	var sign float64 = 1
	var decimal float64 = 1
	var inDecimal bool

	for i := 0; i < len(s); i++ {
		c := s[i]
		if c == '-' {
			sign = -1
		} else if c == '.' {
			inDecimal = true
		} else if c >= '0' && c <= '9' {
			if inDecimal {
				decimal *= 10
				result += float64(c-'0') / decimal
			} else {
				result = result*10 + float64(c-'0')
			}
		}
	}

	return result * sign
}

// Distance calculates Euclidean distance between two points
func Distance(x1, y1, x2, y2 float64) float64 {
	dx := x2 - x1
	dy := y2 - y1
	return math.Sqrt(dx*dx + dy*dy)
}

// Clamp clamps a value between min and max
func Clamp(val, min, max float64) float64 {
	if val < min {
		return min
	}
	if val > max {
		return max
	}
	return val
}

// MinInt returns the minimum of two integers
func MinInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// MaxInt returns the maximum of two integers
func MaxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}
