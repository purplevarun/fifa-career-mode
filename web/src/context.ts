import { createContext, useContext } from "react";
import type { Filters, Match, Model } from "./data";

export const CareerContext = createContext<{
	model: Model;
	filters: Filters;
	matches: Match[];
	openSource: (id: string) => void;
} | null>(null);

export function useCareer() {
	const value = useContext(CareerContext);
	if (!value) throw new Error("Career data context is missing");
	return value;
}
