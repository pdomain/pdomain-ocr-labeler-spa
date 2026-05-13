import { describe, it, expect, beforeEach } from "vitest";
import { useUiPrefs } from "./ui-prefs";

describe("ui-prefs store", () => {
  beforeEach(() => {
    useUiPrefs.setState({
      lineFilter: null,
      layerVisibility: {
        paragraph: true,
        line: true,
        word: true,
      },
      splitterPosition: 0.5,
      selectionMode: "box",
    });
  });

  describe("initialization", () => {
    it("initialises with default values", () => {
      const store = useUiPrefs.getState();
      expect(store.lineFilter).toBeNull();
      expect(store.layerVisibility).toEqual({
        paragraph: true,
        line: true,
        word: true,
      });
      expect(store.splitterPosition).toBe(0.5);
      expect(store.selectionMode).toBe("box");
    });
  });

  describe("lineFilter updates", () => {
    it("updates lineFilter", () => {
      useUiPrefs.setState({ lineFilter: "paragraph_id_123" });
      expect(useUiPrefs.getState().lineFilter).toBe("paragraph_id_123");
    });

    it("clears lineFilter by setting to null", () => {
      useUiPrefs.setState({ lineFilter: "paragraph_id_123" });
      useUiPrefs.setState({ lineFilter: null });
      expect(useUiPrefs.getState().lineFilter).toBeNull();
    });
  });

  describe("layerVisibility updates", () => {
    it("toggles paragraph visibility", () => {
      useUiPrefs.setState((state) => ({
        layerVisibility: {
          ...state.layerVisibility,
          paragraph: false,
        },
      }));
      expect(useUiPrefs.getState().layerVisibility.paragraph).toBe(false);
    });

    it("toggles line visibility", () => {
      useUiPrefs.setState((state) => ({
        layerVisibility: {
          ...state.layerVisibility,
          line: false,
        },
      }));
      expect(useUiPrefs.getState().layerVisibility.line).toBe(false);
    });

    it("toggles word visibility", () => {
      useUiPrefs.setState((state) => ({
        layerVisibility: {
          ...state.layerVisibility,
          word: false,
        },
      }));
      expect(useUiPrefs.getState().layerVisibility.word).toBe(false);
    });

    it("updates multiple layer visibilities at once", () => {
      useUiPrefs.setState({
        layerVisibility: {
          paragraph: false,
          line: true,
          word: false,
        },
      });
      const visibility = useUiPrefs.getState().layerVisibility;
      expect(visibility.paragraph).toBe(false);
      expect(visibility.line).toBe(true);
      expect(visibility.word).toBe(false);
    });
  });

  describe("splitterPosition updates", () => {
    it("updates splitterPosition", () => {
      useUiPrefs.setState({ splitterPosition: 0.7 });
      expect(useUiPrefs.getState().splitterPosition).toBe(0.7);
    });

    it("handles minimum splitter position", () => {
      useUiPrefs.setState({ splitterPosition: 0.1 });
      expect(useUiPrefs.getState().splitterPosition).toBe(0.1);
    });

    it("handles maximum splitter position", () => {
      useUiPrefs.setState({ splitterPosition: 0.9 });
      expect(useUiPrefs.getState().splitterPosition).toBe(0.9);
    });
  });

  describe("selectionMode updates", () => {
    it("updates selectionMode to line", () => {
      useUiPrefs.setState({ selectionMode: "line" });
      expect(useUiPrefs.getState().selectionMode).toBe("line");
    });

    it("updates selectionMode to word", () => {
      useUiPrefs.setState({ selectionMode: "word" });
      expect(useUiPrefs.getState().selectionMode).toBe("word");
    });

    it("defaults to box mode", () => {
      expect(useUiPrefs.getState().selectionMode).toBe("box");
    });
  });

  describe("state persistence", () => {
    it("maintains state across multiple updates", () => {
      useUiPrefs.setState({
        lineFilter: "test_filter",
        splitterPosition: 0.6,
      });
      useUiPrefs.setState({ selectionMode: "line" });

      const state = useUiPrefs.getState();
      expect(state.lineFilter).toBe("test_filter");
      expect(state.splitterPosition).toBe(0.6);
      expect(state.selectionMode).toBe("line");
    });
  });
});
