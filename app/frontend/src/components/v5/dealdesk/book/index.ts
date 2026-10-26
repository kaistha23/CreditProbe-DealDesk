/** PLAN_R12 Session I: the Book's exports for U's shell (Deal Desk "Book" tab and the "Existing deals going bad" card). */
export { BookTab } from "./book-tab";
export { FeedbackView } from "./feedback-view";
export { RarocDriftView, RarocDriftPage, DriftWaterfall } from "../portfolio-raroc";
export { bookApi, fetchBookCounts, FILTERS as BOOK_FILTERS } from "./api";
export type { BookCounts, BookFilter, BookRow, BookList, FacilityDetail, Drift } from "./api";
