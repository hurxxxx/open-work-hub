import type {
  ToleranceAllResponse,
  ToleranceResponse,
} from '../api/dataviz-api';
import { CompressorPerfProfileToleranceSection } from './CompressorPerfProfileToleranceSection';
import { CompressorPerfRefToleranceSection } from './CompressorPerfRefToleranceSection';
import {
  type ProfileToleranceProfiles,
  type ProfileToleranceValues,
  type RefToleranceValues,
} from './compressor-perf-tolerance-model';

export interface CompressorPerfToleranceEditorProps {
  allProfiles: ProfileToleranceProfiles;
  capacity: string;
  carModel: string;
  fieldLabels: Record<string, string>;
  loading: string | null;
  profileName: string;
  profileRowCount: number;
  profileSaveStatus?: string;
  refSaveStatus?: string;
  refValues: RefToleranceValues;
  tolerance: ToleranceResponse | null;
  toleranceAll: ToleranceAllResponse | null;
  toleranceFile: File | null;
  tolValues: ProfileToleranceValues;
  onCapacityChange: (capacity: string) => void;
  onCarModelChange: (carModel: string) => void;
  onProfileNameChange: (name: string) => void;
  onProfileRowCountChange: (count: number) => void;
  onRefreshProfile: () => void | Promise<void>;
  onRefValuesChange: (values: RefToleranceValues) => void;
  onSaveProfile: () => void | Promise<void>;
  onSaveTolerance: () => void | Promise<void>;
  onToleranceFileChange: (file: File | null) => void;
  onToleranceUpload: () => boolean | Promise<boolean>;
  onTolValuesChange: (values: ProfileToleranceValues) => void;
}

export function CompressorPerfToleranceEditor({
  allProfiles,
  capacity,
  carModel,
  fieldLabels,
  loading,
  profileName,
  profileRowCount,
  profileSaveStatus,
  refSaveStatus,
  refValues,
  tolerance,
  toleranceAll,
  toleranceFile,
  tolValues,
  onCapacityChange,
  onCarModelChange,
  onProfileNameChange,
  onProfileRowCountChange,
  onRefreshProfile,
  onRefValuesChange,
  onSaveProfile,
  onSaveTolerance,
  onToleranceFileChange,
  onToleranceUpload,
  onTolValuesChange,
}: CompressorPerfToleranceEditorProps) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-4">
        <CompressorPerfRefToleranceSection
          capacity={capacity}
          carModel={carModel}
          loading={loading}
          refSaveStatus={refSaveStatus}
          refValues={refValues}
          tolerance={tolerance}
          toleranceAll={toleranceAll}
          toleranceFile={toleranceFile}
          onCapacityChange={onCapacityChange}
          onCarModelChange={onCarModelChange}
          onRefValuesChange={onRefValuesChange}
          onSaveTolerance={onSaveTolerance}
          onToleranceFileChange={onToleranceFileChange}
          onToleranceUpload={onToleranceUpload}
        />
      </div>

      <CompressorPerfProfileToleranceSection
        allProfiles={allProfiles}
        fieldLabels={fieldLabels}
        loading={loading}
        profileName={profileName}
        profileRowCount={profileRowCount}
        profileSaveStatus={profileSaveStatus}
        tolValues={tolValues}
        onProfileNameChange={onProfileNameChange}
        onProfileRowCountChange={onProfileRowCountChange}
        onRefreshProfile={onRefreshProfile}
        onSaveProfile={onSaveProfile}
        onTolValuesChange={onTolValuesChange}
      />
    </section>
  );
}
