import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import type { FilterCriteria } from '../types/filters';

interface FilterContextValue {
  /** Current filter criteria shared from the Diagram page */
  filters: FilterCriteria;
  /** Update the shared filter criteria */
  setFilters: (filters: FilterCriteria) => void;
}

const FilterContext = createContext<FilterContextValue | null>(null);

export function FilterProvider({ children }: { children: ReactNode }) {
  const [filters, setFiltersState] = useState<FilterCriteria>({
    tag_filters: [],
    type_filters: [],
    tag_filter_operator: 'AND',
  });

  const setFilters = useCallback((newFilters: FilterCriteria) => {
    setFiltersState(newFilters);
  }, []);

  return (
    <FilterContext.Provider value={{ filters, setFilters }}>
      {children}
    </FilterContext.Provider>
  );
}

export function useFilterContext(): FilterContextValue {
  const context = useContext(FilterContext);
  if (!context) {
    throw new Error('useFilterContext must be used within a FilterProvider');
  }
  return context;
}
