/**
 * Unit tests for the rating scale used by the v5 Early Warning screens. No network.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  RATING_ORDER, compareRatings, isGrade, isRatingName, isRatingValues, orderRatingRows, orderRatingTable, ratingAxis,
  ratingAxisOrder, ratingRank, ratingsInOrder, sortByRating,
} from "./ratings.ts";

test("the scale runs AAA to D, twenty grades, no duplicates", () => {
  assert.equal(RATING_ORDER.length, 20);
  assert.equal(RATING_ORDER[0], "AAA");
  assert.equal(RATING_ORDER[RATING_ORDER.length - 1], "D");
  assert.equal(new Set(RATING_ORDER).size, RATING_ORDER.length);
});

test("ratingRank follows the scale; unknown and missing go last", () => {
  assert.equal(ratingRank("AAA"), 0);
  assert.equal(ratingRank("BBB-"), RATING_ORDER.indexOf("BBB-"));
  assert.equal(ratingRank("D"), 19);
  assert.equal(ratingRank(" bb+ "), RATING_ORDER.indexOf("BB+"));
  assert.equal(ratingRank("NR"), RATING_ORDER.length);
  assert.equal(ratingRank(""), RATING_ORDER.length);
  assert.equal(ratingRank(null), RATING_ORDER.length);
  assert.equal(ratingRank(undefined), RATING_ORDER.length);
});

test("compareRatings orders best first, notches inside a letter grade", () => {
  assert.ok(compareRatings("AA+", "AA") < 0);
  assert.ok(compareRatings("AA", "AA-") < 0);
  assert.ok(compareRatings("BBB-", "BB+") < 0);
  assert.ok(compareRatings("C", "CCC") > 0);
  assert.equal(compareRatings("A", "A"), 0);
  assert.ok(compareRatings("D", "NR") < 0);
  assert.ok(compareRatings("NR", "WD") < 0, "unknowns tie on rank and fall back to name");
});

test("sortByRating returns a sorted copy and keeps ties in input order", () => {
  const rows = [
    { rating: "B", n: 1 }, { rating: "NR", n: 2 }, { rating: "AA-", n: 3 },
    { rating: "BBB", n: 4 }, { rating: "B", n: 5 }, { rating: "AAA", n: 6 }, { rating: "CCC", n: 7 },
  ];
  const before = rows.map((r) => r.n);
  const sorted = sortByRating(rows, "rating");
  assert.deepEqual(sorted.map((r) => r.rating), ["AAA", "AA-", "BBB", "B", "B", "CCC", "NR"]);
  assert.deepEqual(sorted.filter((r) => r.rating === "B").map((r) => r.n), [1, 5]);
  assert.deepEqual(rows.map((r) => r.n), before, "input not mutated");
});

test("orderRatingTable sorts a table whose first column holds grades (R6 E3)", () => {
  const cols = [{ key: "rating" }, { key: "ead" }];
  const rows = [{ rating: "BB", ead: 900 }, { rating: "AAA", ead: 10 }, { rating: "CCC", ead: 50 },
    { rating: "A-", ead: 700 }, { rating: "Total", ead: 1660 }];
  assert.deepEqual(orderRatingTable(rows, cols).map((r) => r.rating), ["AAA", "A-", "BB", "CCC", "Total"]);
  // a borrower list that merely shows a rating keeps its own order
  const names = [{ name: "Zeta", rating: "B" }, { name: "Alpha", rating: "AAA" }];
  assert.deepEqual(orderRatingTable(names, ["name", "rating"]), names);
  // markdown rows (arrays): column 0
  assert.deepEqual(orderRatingTable([["C", "1"], ["CC", "2"], ["CCC", "3"], ["D", "4"]]).map((r) => r[0]), ["CCC", "CC", "C", "D"]);
  assert.deepEqual(orderRatingTable([], cols), []);
});

test("orderRatingRows leaves non-rating columns alone; ratingAxis pins Plotly categories", () => {
  const rows = [{ s: "Retail" }, { s: "Energy" }];
  assert.deepEqual(orderRatingRows(rows, "s"), rows);
  assert.deepEqual(ratingAxis(["BBB", "AA", "D", "AA"]), { categoryorder: "array", categoryarray: ["AA", "BBB", "D"] });
  assert.deepEqual(ratingAxis(["Energy", "Retail"]), {});
  assert.deepEqual(ratingAxisOrder(["NR", "B", "A"]), ["A", "B", "NR"]);
});

test("ratingsInOrder flags a sequence out of the global order", () => {
  assert.ok(ratingsInOrder(["AAA", "AA+", "AA", "BBB", "CCC", "CC", "C", "D"]));
  assert.ok(ratingsInOrder(["Rating", "A", "B", "Total"]));
  assert.ok(!ratingsInOrder(["A", "AA", "AAA"]));
  assert.ok(!ratingsInOrder(["C", "CC", "CCC"]));
  assert.ok(isGrade(" bbb- ") && !isGrade("NR") && isRatingName("internal_rating") && !isRatingName("sector"));
  assert.ok(isRatingValues(["A", "B", null, "Overall"]) && !isRatingValues(["A", "Energy"]) && !isRatingValues(["A"]));
});

test("sortByRating puts every scale grade in RATING_ORDER", () => {
  const shuffled = [...RATING_ORDER].reverse().map((rating) => ({ rating }));
  assert.deepEqual(sortByRating(shuffled, "rating").map((r) => r.rating), [...RATING_ORDER]);
});
