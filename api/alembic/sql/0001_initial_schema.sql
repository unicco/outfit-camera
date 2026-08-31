CREATE TYPE public.clothingcategory AS ENUM (
    'TOPS',
    'BOTTOMS',
    'SHOES',
    'OUTERWEAR',
    'ACCESSORIES',
    'UNDERWEAR',
    'DRESSES',
    'SETS',
    'BAG',
    'OTHER'
);


ALTER TYPE public.clothingcategory OWNER TO coordinate_user;


CREATE TYPE public.clothingstatus AS ENUM (
    'ACTIVE',
    'STORED',
    'DONATED',
    'SOLD',
    'RETIRED',
    'SELL_CANDIDATE'
);


ALTER TYPE public.clothingstatus OWNER TO coordinate_user;


CREATE TYPE public.confidencelevel AS ENUM (
    'VERY_LOW',
    'LOW',
    'MEDIUM',
    'HIGH',
    'VERY_HIGH'
);


ALTER TYPE public.confidencelevel OWNER TO coordinate_user;


CREATE TYPE public.feedbacktype AS ENUM (
    'MATCH_CORRECT',
    'MATCH_INCORRECT',
    'ITEM_MISSING',
    'ITEM_FALSE_POSITIVE',
    'COLOR_INCORRECT',
    'CATEGORY_INCORRECT'
);


ALTER TYPE public.feedbacktype OWNER TO coordinate_user;




CREATE TABLE public.ai_detection_feedback (
    id uuid NOT NULL,
    photo_id character varying(255) NOT NULL,
    detection_session_id character varying(255),
    predicted_category character varying(50),
    predicted_confidence double precision,
    predicted_bbox json,
    predicted_wardrobe_matches json,
    feedback_type public.feedbacktype NOT NULL,
    is_correct boolean NOT NULL,
    correct_category character varying(50),
    correct_wardrobe_item_id character varying(255),
    user_confidence public.confidencelevel,
    feedback_notes text,
    image_metadata json,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone,
    predicted_pattern character varying(50),
    correct_pattern character varying(50)
);


ALTER TABLE public.ai_detection_feedback OWNER TO coordinate_user;







CREATE TABLE public.category_co_occurrences (
    category_1 character varying(50) NOT NULL,
    category_2 character varying(50) NOT NULL,
    subcategory_1 character varying(50) NOT NULL,
    subcategory_2 character varying(50) NOT NULL,
    co_occurrence_count integer DEFAULT 0 NOT NULL,
    total_occurrences integer DEFAULT 0 NOT NULL,
    probability double precision DEFAULT '0'::double precision NOT NULL,
    season character varying(20) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.category_co_occurrences OWNER TO coordinate_user;


COMMENT ON TABLE public.category_co_occurrences IS 'カテゴリレベルの共起パターンを追跡';



COMMENT ON COLUMN public.category_co_occurrences.season IS '季節別の統計（spring, summer, autumn, winter）';



CREATE TABLE public.clothing_items (
    id character varying(36) NOT NULL,
    name character varying(255) NOT NULL,
    category character varying(100) NOT NULL,
    subcategory character varying(50),
    brand character varying(100),
    pattern character varying(50),
    material character varying(100),
    size character varying(20),
    purchase_date date,
    purchase_price double precision,
    season json,
    occasion json,
    care_instructions text,
    status character varying(50) NOT NULL,
    image_urls json,
    image_metadata json,
    tags json,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    last_used_date date,
    default_usage_count integer DEFAULT 0,
    usage_count integer DEFAULT 0,
    embedding_vector json,
    embedding_computed_at timestamp with time zone,
    embedding_model_version character varying(50),
    colors_palette json,
    purchase_location character varying(200),
    sale_platform character varying(50),
    sale_price real,
    sale_commission real,
    disposal_date date
);


ALTER TABLE public.clothing_items OWNER TO coordinate_user;


CREATE TABLE public.co_occurrence_learning_stats (
    id character varying(36) NOT NULL,
    batch_date date NOT NULL,
    learning_type character varying(20) NOT NULL,
    records_processed integer NOT NULL,
    new_patterns_found integer NOT NULL,
    patterns_updated integer NOT NULL,
    processing_time_ms double precision,
    status character varying(20) DEFAULT 'completed'::character varying NOT NULL,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.co_occurrence_learning_stats OWNER TO coordinate_user;


COMMENT ON TABLE public.co_occurrence_learning_stats IS '共起学習のバッチ処理履歴';



COMMENT ON COLUMN public.co_occurrence_learning_stats.learning_type IS 'item_pair, category';



CREATE TABLE public.daily_outfit_logs (
    id character varying(36) NOT NULL,
    capture_date date NOT NULL,
    photo_id character varying(36),
    worn_item_ids json NOT NULL,
    worn_categories json NOT NULL,
    weather_info json,
    occasion character varying(50),
    user_rating integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.daily_outfit_logs OWNER TO coordinate_user;


COMMENT ON TABLE public.daily_outfit_logs IS '日次の着用記録から学習データを生成';



COMMENT ON COLUMN public.daily_outfit_logs.worn_item_ids IS '着用アイテムIDのリスト';



COMMENT ON COLUMN public.daily_outfit_logs.worn_categories IS '着用カテゴリの集計';



COMMENT ON COLUMN public.daily_outfit_logs.weather_info IS '天気情報（将来の拡張用）';



COMMENT ON COLUMN public.daily_outfit_logs.occasion IS '着用シーン（casual, business, formal等）';



COMMENT ON COLUMN public.daily_outfit_logs.user_rating IS 'ユーザーの満足度評価（1-5）';



CREATE TABLE public.photos (
    id character varying(36) NOT NULL,
    filename character varying(255) NOT NULL,
    file_path character varying(500) NOT NULL,
    file_size integer,
    resolution_width integer,
    resolution_height integer,
    captured_at timestamp with time zone NOT NULL,
    source character varying(50) NOT NULL,
    person_detected boolean NOT NULL,
    confidence_score double precision,
    detection_count integer NOT NULL,
    clothing_items json,
    processing_time_ms double precision,
    model_version character varying(50),
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    ai_detection_results json,
    ai_detection_status character varying(20),
    ai_detection_error character varying(500),
    ai_cropped_images json,
    embedding_vector json,
    embedding_computed_at timestamp with time zone,
    embedding_model_version character varying(50)
);


ALTER TABLE public.photos OWNER TO coordinate_user;


CREATE VIEW public.daily_summary AS
 SELECT date(photos.captured_at) AS date,
    count(*) FILTER (WHERE (photos.deleted_at IS NULL)) AS total_count,
    count(*) FILTER (WHERE ((photos.person_detected = true) AND (photos.deleted_at IS NULL))) AS person_count,
    max(photos.captured_at) FILTER (WHERE (photos.deleted_at IS NULL)) AS last_capture_time
   FROM public.photos
  GROUP BY (date(photos.captured_at))
  ORDER BY (date(photos.captured_at)) DESC;


ALTER TABLE public.daily_summary OWNER TO coordinate_user;


CREATE TABLE public.detection_results (
    id character varying(36) NOT NULL,
    photo_id character varying(36) NOT NULL,
    detection_type character varying(50) NOT NULL,
    model_name character varying(100) NOT NULL,
    model_version character varying(50),
    detection_results json,
    confidence_score double precision,
    processing_time_ms double precision,
    embedding_vector json,
    embedding_dimension integer,
    status character varying(20) DEFAULT 'completed'::character varying NOT NULL,
    error_message character varying(500),
    cache_hit boolean DEFAULT false NOT NULL,
    cache_key character varying(255),
    detected_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL
);


ALTER TABLE public.detection_results OWNER TO coordinate_user;


CREATE TABLE public.item_pair_co_occurrences (
    item_id_1 character varying(36) NOT NULL,
    item_id_2 character varying(36) NOT NULL,
    co_occurrence_count integer DEFAULT 0 NOT NULL,
    last_worn_date date,
    confidence_score double precision,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.item_pair_co_occurrences OWNER TO coordinate_user;


COMMENT ON TABLE public.item_pair_co_occurrences IS '具体的なアイテムペアの共起頻度を追跡';



COMMENT ON COLUMN public.item_pair_co_occurrences.confidence_score IS '組み合わせの信頼度スコア (0-1)';



CREATE TABLE public.learning_dataset (
    id uuid NOT NULL,
    photo_id character varying(255) NOT NULL,
    dataset_type character varying(50) NOT NULL,
    ground_truth_items json NOT NULL,
    label_quality_score double precision,
    image_quality_score double precision,
    labeled_by character varying(100),
    validation_count integer NOT NULL,
    used_in_training boolean NOT NULL,
    training_epochs json,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


ALTER TABLE public.learning_dataset OWNER TO coordinate_user;


CREATE TABLE public.matching_accuracy_metrics (
    id uuid NOT NULL,
    date timestamp with time zone NOT NULL,
    evaluation_period character varying(20) NOT NULL,
    total_detections integer NOT NULL,
    correct_detections integer NOT NULL,
    false_positives integer NOT NULL,
    false_negatives integer NOT NULL,
    category_accuracy json,
    color_accuracy double precision,
    total_matches integer NOT NULL,
    correct_matches integer NOT NULL,
    match_accuracy double precision,
    avg_detection_confidence double precision,
    avg_match_confidence double precision,
    model_version character varying(50),
    algorithm_version character varying(50),
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.matching_accuracy_metrics OWNER TO coordinate_user;


CREATE TABLE public.model_performance_history (
    id uuid NOT NULL,
    model_version character varying(50) NOT NULL,
    algorithm_type character varying(50) NOT NULL,
    training_date timestamp with time zone,
    "precision" double precision,
    recall double precision,
    f1_score double precision,
    map_score double precision,
    category_performance json,
    training_dataset_size integer,
    validation_dataset_size integer,
    test_dataset_size integer,
    training_time_hours double precision,
    inference_time_ms double precision,
    model_size_mb double precision,
    is_production boolean NOT NULL,
    deployment_date timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.model_performance_history OWNER TO coordinate_user;


CREATE TABLE public.outfit_items (
    id character varying(36) NOT NULL,
    outfit_record_id character varying(36) NOT NULL,
    clothing_item_id character varying(36) NOT NULL,
    worn_condition character varying(100),
    styling_notes text,
    created_at timestamp with time zone DEFAULT now(),
    detection_confidence real,
    manual_added boolean DEFAULT false,
    position_x integer,
    position_y integer
);


ALTER TABLE public.outfit_items OWNER TO coordinate_user;


CREATE TABLE public.outfit_records (
    id character varying(36) NOT NULL,
    photo_id character varying(255) NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    confidence_score double precision,
    manual_selection boolean NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.outfit_records OWNER TO coordinate_user;


CREATE TABLE public.search_logs (
    id character varying NOT NULL,
    capture_id character varying,
    detected_item_id character varying NOT NULL,
    detected_category character varying NOT NULL,
    detected_embedding jsonb,
    detected_description text,
    search_k integer DEFAULT 20 NOT NULL,
    "timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    is_manual_correction boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.search_logs OWNER TO coordinate_user;


CREATE TABLE public.search_result_items (
    id character varying NOT NULL,
    search_log_id character varying NOT NULL,
    wardrobe_item_id character varying NOT NULL,
    rank integer NOT NULL,
    embedding_similarity double precision NOT NULL,
    color_histogram_distance double precision,
    texture_similarity double precision,
    co_occurrence_score double precision,
    final_score double precision NOT NULL,
    is_correct boolean,
    user_feedback character varying,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.search_result_items OWNER TO coordinate_user;


ALTER TABLE ONLY public.ai_detection_feedback
    ADD CONSTRAINT ai_detection_feedback_pkey PRIMARY KEY (id);






ALTER TABLE ONLY public.category_co_occurrences
    ADD CONSTRAINT category_co_occurrences_pkey PRIMARY KEY (category_1, category_2, subcategory_1, subcategory_2, season);



ALTER TABLE ONLY public.clothing_items
    ADD CONSTRAINT clothing_items_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.co_occurrence_learning_stats
    ADD CONSTRAINT co_occurrence_learning_stats_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.daily_outfit_logs
    ADD CONSTRAINT daily_outfit_logs_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.detection_results
    ADD CONSTRAINT detection_results_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.item_pair_co_occurrences
    ADD CONSTRAINT item_pair_co_occurrences_pkey PRIMARY KEY (item_id_1, item_id_2);



ALTER TABLE ONLY public.learning_dataset
    ADD CONSTRAINT learning_dataset_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.matching_accuracy_metrics
    ADD CONSTRAINT matching_accuracy_metrics_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.model_performance_history
    ADD CONSTRAINT model_performance_history_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.outfit_items
    ADD CONSTRAINT outfit_items_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.outfit_records
    ADD CONSTRAINT outfit_records_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.photos
    ADD CONSTRAINT photos_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.search_logs
    ADD CONSTRAINT search_logs_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.search_result_items
    ADD CONSTRAINT search_result_items_pkey PRIMARY KEY (id);



ALTER TABLE ONLY public.daily_outfit_logs
    ADD CONSTRAINT uq_daily_outfit_date_photo UNIQUE (capture_date, photo_id);



CREATE INDEX idx_active_photos ON public.photos USING btree (deleted_at, captured_at);



CREATE INDEX idx_captured_at ON public.photos USING btree (captured_at);



CREATE INDEX idx_category_co_occur_prob ON public.category_co_occurrences USING btree (probability);



CREATE INDEX idx_category_co_occur_season ON public.category_co_occurrences USING btree (season);



CREATE INDEX idx_clothing_category ON public.clothing_items USING btree (category);



CREATE INDEX idx_clothing_category_status ON public.clothing_items USING btree (category, status);



CREATE INDEX idx_clothing_status ON public.clothing_items USING btree (status);



CREATE INDEX idx_daily_outfit_date ON public.daily_outfit_logs USING btree (capture_date);



CREATE INDEX idx_daily_outfit_photo ON public.daily_outfit_logs USING btree (photo_id);



CREATE INDEX idx_dataset_photo_id ON public.learning_dataset USING btree (photo_id);



CREATE INDEX idx_dataset_type ON public.learning_dataset USING btree (dataset_type);



CREATE INDEX idx_detection_results_cache_key ON public.detection_results USING btree (cache_key);



CREATE INDEX idx_detection_results_detected_at ON public.detection_results USING btree (detected_at);



CREATE INDEX idx_detection_results_model ON public.detection_results USING btree (model_name, model_version);



CREATE INDEX idx_detection_results_photo_id ON public.detection_results USING btree (photo_id);



CREATE INDEX idx_detection_results_photo_type ON public.detection_results USING btree (photo_id, detection_type);



CREATE INDEX idx_detection_results_status ON public.detection_results USING btree (status);



CREATE INDEX idx_feedback_created_at ON public.ai_detection_feedback USING btree (created_at);



CREATE INDEX idx_feedback_photo_id ON public.ai_detection_feedback USING btree (photo_id);



CREATE INDEX idx_feedback_type ON public.ai_detection_feedback USING btree (feedback_type);



CREATE INDEX idx_item_pair_co_occur_count ON public.item_pair_co_occurrences USING btree (co_occurrence_count);



CREATE INDEX idx_item_pair_item2 ON public.item_pair_co_occurrences USING btree (item_id_2);



CREATE INDEX idx_item_pair_last_worn ON public.item_pair_co_occurrences USING btree (last_worn_date);



CREATE INDEX idx_learning_stats_date ON public.co_occurrence_learning_stats USING btree (batch_date);



CREATE INDEX idx_learning_stats_type ON public.co_occurrence_learning_stats USING btree (learning_type);



CREATE INDEX idx_metrics_date ON public.matching_accuracy_metrics USING btree (date);



CREATE INDEX idx_metrics_period ON public.matching_accuracy_metrics USING btree (evaluation_period);



CREATE INDEX idx_outfit_records_photo_id ON public.outfit_records USING btree (photo_id);



CREATE INDEX idx_outfit_records_recorded_at ON public.outfit_records USING btree (recorded_at);



CREATE INDEX idx_performance_model ON public.model_performance_history USING btree (model_version);



CREATE INDEX idx_performance_production ON public.model_performance_history USING btree (is_production);



CREATE INDEX idx_person_detected ON public.photos USING btree (person_detected, deleted_at);



CREATE INDEX ix_ai_detection_feedback_photo_id ON public.ai_detection_feedback USING btree (photo_id);



CREATE INDEX ix_clothing_items_category ON public.clothing_items USING btree (category);



CREATE INDEX ix_learning_dataset_photo_id ON public.learning_dataset USING btree (photo_id);



CREATE INDEX ix_matching_accuracy_metrics_date ON public.matching_accuracy_metrics USING btree (date);



CREATE INDEX ix_model_performance_history_model_version ON public.model_performance_history USING btree (model_version);



CREATE INDEX ix_outfit_records_photo_id ON public.outfit_records USING btree (photo_id);



CREATE INDEX ix_photos_captured_at ON public.photos USING btree (captured_at);



CREATE INDEX ix_photos_deleted_at ON public.photos USING btree (deleted_at);



CREATE UNIQUE INDEX ix_photos_filename ON public.photos USING btree (filename);



CREATE INDEX ix_photos_person_detected ON public.photos USING btree (person_detected);



CREATE INDEX ix_search_logs_capture_id ON public.search_logs USING btree (capture_id);



CREATE INDEX ix_search_logs_timestamp ON public.search_logs USING btree ("timestamp");



CREATE INDEX ix_search_result_items_is_correct ON public.search_result_items USING btree (is_correct);



CREATE INDEX ix_search_result_items_search_log_id ON public.search_result_items USING btree (search_log_id);



CREATE INDEX ix_search_result_items_wardrobe_item_id ON public.search_result_items USING btree (wardrobe_item_id);



ALTER TABLE ONLY public.daily_outfit_logs
    ADD CONSTRAINT daily_outfit_logs_photo_id_fkey FOREIGN KEY (photo_id) REFERENCES public.photos(id) ON DELETE SET NULL;



ALTER TABLE ONLY public.detection_results
    ADD CONSTRAINT detection_results_photo_id_fkey FOREIGN KEY (photo_id) REFERENCES public.photos(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.item_pair_co_occurrences
    ADD CONSTRAINT item_pair_co_occurrences_item_id_1_fkey FOREIGN KEY (item_id_1) REFERENCES public.clothing_items(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.item_pair_co_occurrences
    ADD CONSTRAINT item_pair_co_occurrences_item_id_2_fkey FOREIGN KEY (item_id_2) REFERENCES public.clothing_items(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.outfit_items
    ADD CONSTRAINT outfit_items_clothing_item_id_fkey FOREIGN KEY (clothing_item_id) REFERENCES public.clothing_items(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.outfit_items
    ADD CONSTRAINT outfit_items_outfit_record_id_fkey FOREIGN KEY (outfit_record_id) REFERENCES public.outfit_records(id) ON DELETE CASCADE;



ALTER TABLE ONLY public.search_result_items
    ADD CONSTRAINT search_result_items_search_log_id_fkey FOREIGN KEY (search_log_id) REFERENCES public.search_logs(id);



ALTER TABLE ONLY public.search_result_items
    ADD CONSTRAINT search_result_items_wardrobe_item_id_fkey FOREIGN KEY (wardrobe_item_id) REFERENCES public.clothing_items(id);



GRANT ALL ON SCHEMA public TO coordinate_user;
